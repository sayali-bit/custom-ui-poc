from .input_func import InputFuncType, AsyncInputFunc, SyncInputFunc
from autogen_agentchat.messages import TextMessage, MultiModalMessage

from autogen_core import CancellationToken, Image, EVENT_LOGGER_NAME
from autogen_core.models import (
    ChatCompletionClient,
    LLMMessage,
    SystemMessage,
)

from inspect import iscoroutinefunction

import json

from contextlib import contextmanager
from contextvars import ContextVar

import asyncio
from typing import (
    Any,
    Optional,
    TypedDict,
    cast,
    ClassVar,
    Generator,
    List,
    Literal,
    Protocol,
)

from dataclasses import dataclass
import logging


"""
The ActionGuard protocol is used to check if an action is irreversisble.

The three possible values are:
- "always": The action is always irreversible.
- "maybe": The action is maybe irreversible.
- "never": The action is never irreversible.
"""
MaybeRequiresApproval = Literal["always", "maybe", "never"]

DEFAULT_REQUIRES_APPROVAL: MaybeRequiresApproval = "always"


class BaseApprovalGuard(Protocol):
    async def requires_approval(
        self,
        baseline: MaybeRequiresApproval,
        llm_guess: MaybeRequiresApproval,
        action_context: List[LLMMessage],
    ) -> bool:
        """Check if the action is irreversible; only called if the tool is marked 'maybe' irreversible."""
        ...

    async def get_approval(
        self, action_description: TextMessage | MultiModalMessage
    ) -> bool:
        """Get approval for the action; only called if the tool is marked 'always' irreversible, or
        'maybe' irreversible if the ."""
        ...


# TypedDictionary for JSON
# Scehma: { "accepted": bool, "content": str }
class UserInputResponse(TypedDict):
    accepted: bool
    content: str


@dataclass
class ApprovalConfig:
    approval_policy: Literal[
        "always", "never", "auto-conservative", "auto-permissive"
    ] = "never"


# This works around our inability to pass a callback-wrapper object through the ComponentConfig
# system, since it is designed for serialization/deserialization of the config object.
# TODO: Figure out how to include callbacks in ComponentConfig-based object initialization
class ApprovalGuardContext:
    def __init__(self) -> None:
        raise RuntimeError(
            "InputRequestContext cannot be instantiated. It is a static class that provides context management for user input requests."
        )

    _APPROVAL_GUARD_CONTEXT_VAR: ClassVar[ContextVar[BaseApprovalGuard | None]] = (
        ContextVar("_APPROVAL_GUARD_CONTEXT_VAR")
    )

    @classmethod
    @contextmanager
    def populate_context(
        cls, ctx: BaseApprovalGuard | None
    ) -> Generator[None, Any, None]:
        """:meta private:"""
        token = ApprovalGuardContext._APPROVAL_GUARD_CONTEXT_VAR.set(ctx)
        try:
            yield
        finally:
            ApprovalGuardContext._APPROVAL_GUARD_CONTEXT_VAR.reset(token)

    @classmethod
    def approval_guard(cls) -> BaseApprovalGuard | None:
        try:
            return cls._APPROVAL_GUARD_CONTEXT_VAR.get()
        except LookupError as e:
            raise RuntimeError(
                "ApprovalGuardContext.approval_guard() should only be called when initializing a WebSurfer agent during Team creation."
            ) from e


IRREVERSIBLE_CHECK_PROMPT_TEMPLATE = """
The following action is being proposed:

{approval_message}

Please review this action in the context of the following history, and determine if it requires human approval.
An action requires human approval if it is irreversible or is potentially harmful or impactful.

Please evaluate this action carefully considering the following criteria:
- Does the action have potential real-world consequences affecting user safety or security?
- Could the action cause irreversible changes or require complex steps to undo?
- Does the action impact data integrity, privacy, or significant system state?
- Could the action affect other users or external entities in any impactful way?

If the answer to any of the above is yes, the action should be considered harmful or impactful and require explicit user approval.

Examples for when the action should require human approval:
- If the websurfer is about to click a button that submits a form, or sends an email, or make a purchase, it should require human approval.
- If the websurfer is typing potentially sensitive information, it should require human approval.
- If the coder is writing code that creates files that were not approved or leaks information about the underlying system, it should require human approval.
- If the filesurfer wants to open a file that seems malicious, it should require human approval.

Examples for when the action should not require human approval:
- If the websurfer is about to click a button that changes focus in a UI, it should not require human approval.
- If the websurfer is entering a search query into a search engine that is not sensitive, it should not require human approval.
- If the coder is writing code that is not harmful or creating or opening files, it should not require human approval.

This is not an exhaustive list.

When unsure, err on the side of caution and require human approval.

Please respond with "YES" (requires human approval) or "NO" (does not require human approval) ONLY to indicate your decision.
"""


class ApprovalGuard(BaseApprovalGuard):
    def __init__(
        self,
        input_func: Optional[InputFuncType] = None,
        default_approval: bool = True,
        model_client: Optional[ChatCompletionClient] = None,
        config: Optional[ApprovalConfig] = None,
    ):
        self.model_client = model_client
        self.input_func = input_func
        self._is_async = iscoroutinefunction(input_func)
        self.default_approval = default_approval

        self.config = config or ApprovalConfig()

        self.logger = logging.getLogger(f"{EVENT_LOGGER_NAME}.ApprovalGuard")

    async def _get_input(
        self, prompt: str, cancellation_token: Optional[CancellationToken]
    ) -> str:
        """Handle input based on function signature."""
        try:
            if self._is_async:
                # Cast to AsyncInputFunc for proper typing
                async_func = cast(AsyncInputFunc, self.input_func)
                return await async_func(prompt, cancellation_token, "approval")
            else:
                # Cast to SyncInputFunc for proper typing
                sync_func = cast(SyncInputFunc, self.input_func)
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, sync_func, prompt, "approval")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to get user input: {str(e)}") from e

    async def requires_approval(
        self,
        baseline: MaybeRequiresApproval,
        llm_guess: MaybeRequiresApproval,
        action_context: list[LLMMessage],
    ) -> bool:
        if self.config.approval_policy == "always":
            return True

        if self.config.approval_policy == "never":
            return False

        # smart approval policy
        if baseline == "never":
            return False
        elif baseline == "always":
            return True

        if self.config.approval_policy == "auto-permissive":
            if llm_guess == "never":
                return False
            else:
                return True

        else:
            # auto-conservative policy mode
            # baseline == "maybe"
            if self.model_client is None:
                return self.default_approval
            action_proposal = action_context[-1] if action_context else None
            if action_proposal is None:
                return (
                    self.default_approval
                )  # TODO: Should we require an approval if we have no context?

            check_prompt = IRREVERSIBLE_CHECK_PROMPT_TEMPLATE.format(
                approval_message=action_proposal.content
            )
            system_message = SystemMessage(content=check_prompt)

            selected_context = action_context[:-1]
            if len(selected_context) > 5:
                selected_context = selected_context[-5:]

            request_messages = [system_message]

            result = await self.model_client.create(request_messages)

            if not (isinstance(result.content, str)):
                self.logger.warning(
                    "Model did not return a string response. Defaulting to True for irreversibility check."
                )
                return True

            self.logger.info(
                f"Checking action irreversibility for {action_proposal.content}:\n\n\t--- {result.content}"
            )

            if result.content.lower() in ["yes", "y"]:
                return True
            elif result.content.lower() in ["no", "n"]:
                return False
            else:
                self.logger.warning(
                    "Model did not return a valid response. Expected 'yes' or 'no'. Defaulting to True for irreversibility check."
                )
                return True

    async def get_approval(
        self, action_description: TextMessage | MultiModalMessage
    ) -> bool:
        if self.input_func is None:
            return self.default_approval

        # Use the input function to get user approval
        action_description_str: str
        if isinstance(action_description, TextMessage):
            action_description_str = action_description.content
        elif isinstance(action_description, MultiModalMessage):
            action_description_str = ""
            for content in action_description.content:
                if isinstance(content, str):
                    action_description_str += "\n" + content
                elif isinstance(content, Image):
                    action_description_str += "\n[Image]"

        result_or_json = await self._get_input(action_description_str, None)

        if isinstance(result_or_json, str):
            result_or_json = result_or_json.strip()

        # does result_or_json start with "{"?
        if result_or_json.startswith("{"):
            try:
                # { accepted: true/false, content: "..." }
                result = json.loads(result_or_json)
                if isinstance(result, dict) and "accepted" in result:
                    return bool(result["accepted"])  # type: ignore
                else:
                    return self.default_approval

            except json.JSONDecodeError:
                pass

        if result_or_json.lower() in [
            "accept",
            "yes",
            "y",
            "I don't know. Use your best judgment.",
        ]:
            return True
        elif result_or_json.lower() in ["deny", "no", "n"]:
            return False
        else:
            # If the input is not recognized, default to the default_approval
            return self.default_approval
