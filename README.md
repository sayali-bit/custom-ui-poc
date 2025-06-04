# 🧪 Custom Magentic-UI Prototype

This repository contains a customized version of the [Magentic-UI](https://github.com/microsoft/magentic-ui) prototype originally developed by Microsoft. It includes frontend modifications such as a new color scheme and dark/light mode support.

## 🚀 Quick Start Guide

### 🧱 Backend Setup (Magentic-UI)

1. Clone the repository  
```bash
git clone https://github.com/sayali-bit/custom-ui-poc.git
cd custom-ui-poc/
```

2. Install `uv` if not already installed  
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

3. Create and activate virtual environment  
```bash
uv venv --python=3.12 .venv
. .venv/bin/activate
```

4. Install Magentic-UI backend  
```bash
uv pip install magentic-ui
```

5. Ensure Docker is running  
Playwright requires Docker to manage browser sessions.

6. Run the Magentic UI server  
```bash
magentic ui --port 8081
```

7. Access the running app  
Open [http://localhost:8081](http://localhost:8081) in your browser.  
👉 This is the original prototype UI provided by Microsoft.

---

### 🎨 Custom Frontend Setup

1. Install Node.js via NVM  
```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
source ~/.bashrc  # or ~/.zshrc depending on your shell
nvm install node
```

2. Set up the frontend  
```bash
cd frontend
npm install -g gatsby-cli
npm install --global yarn
yarn install
cp .env.default .env.development
```

3. Run the custom frontend  
```bash
npm run start
```

---

Now the customized frontend should be running at http://localhost:8000

## 📦 Repo Structure

- `app/` – Backend logic (FastAPI)  
- `frontend/` – Customized React frontend (Gatsby + Yarn)  
- `.venv/` – Python virtual environment  
- `.env.development` – Gatsby environment variables  

---

## 📌 Notes

- Make sure Docker is running **before** launching the backend.  
- The customized frontend works independently and can be styled further as needed.  
- This setup supports agent-based browsing and task streaming via Magentic's backend.

---

## 📝 License

This project builds on top of [Magentic-UI](https://github.com/microsoft/magentic-ui), licensed under the [MIT License](https://opensource.org/licenses/MIT). All customizations are for internal use.
