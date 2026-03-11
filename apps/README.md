# Foundry People – Local Development Setup

This repository serves as the central hub for the Foundry People ecosystem, managing everything from AI orchestration to employee portals.

---

## 📦 Repository Overview

- 🐳 **Backend API**: FastAPI  
- 🐘 **Database**: PostgreSQL  
- 🤖 **AI Orchestrator**: Internal Service  
- 🌐 **Web Employee Portal**: Next.js  
- 🌐 **Web Employer Portal**: Next.js  
- 📱 **Mobile App**: Expo  
- 📱 **Mobile Executive App**: Expo  

---

## 1️⃣ Create Python Virtual Environment

From the root `2026/` directory:

```bash
conda create -n empower_llc python=3.11
conda activate empower_llc
```

---

## 2️⃣ Start Infrastructure (Docker)

From the root directory:

```bash
docker compose up --build
```

### Services Started

| Service          | Port  |
|------------------|-------|
| Postgres         | 5432  |
| Backend API      | 8000  |
| AI Orchestrator  | Internal |

Backend API available at:

```
http://localhost:8000
```

To stop services:

```bash
docker compose down
```

---

## 3️⃣ Backend Environment Variables

The backend requires a `.env` file at the root level.

Example:

```env
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=empower
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
INTERNAL_AI_SECRET=your_secret_here
```

---

## 4️⃣ Web Employee Portal

**Directory:** `apps/web-employee`

### Setup

```bash
cd apps/web-employee
cp .env.local.example .env.local
```

### Configuration

Edit `.env.local`:

```env
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=YOUR_ANON_KEY
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
NEXT_PUBLIC_API_WS=ws://localhost:8000
```

link to the website- https://supabase.com/dashboard/project/cyosmjplytvlgzkiymek


### Run

```bash
npm install
npm run dev
```

Runs on:

```
http://localhost:3000
```

---

## 5️⃣ Web Employer Portal

**Directory:** `apps/web-employer`

### Setup

```bash
cd apps/web-employer
cp .env.local.example .env.local
```

### Configuration

Edit `.env.local` (same structure as employee portal):

```env
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=YOUR_ANON_KEY
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api
NEXT_PUBLIC_API_WS=ws://localhost:8000
```

### Run

```bash
npm install
npm run dev
```

Runs on:

```
http://localhost:3001
```

(if 3000 is already in use)

---

## 6️⃣ Mobile App (Employee)

**Directory:** `apps/mobile`

### Setup

```bash
cd apps/mobile
ulimit -n 65536
npm install
npm install typescript@~5.3.3 @types/react@~18.2.79 --save-dev
```

### Run

```bash
npx expo start
```

Scan the QR code with Expo Go.

Metro will run on:

```
exp://<your-local-ip>:8081
```

---

## 7️⃣ Mobile Executive App

**Directory:** `apps/mobile-exec/mobile-exec-fixed`

### Setup

```bash
cd apps/mobile-exec/mobile-exec-fixed
ulimit -n 65536
npm install
npm install typescript@~5.3.3 @types/react@~18.2.79 --save-dev
```

#### curl command to test-

```bash
curl -X POST http://localhost:8000/ws/test-broadcast \
  -H "Content-Type: application/json" \
  -d '{"id":"test-002","title":"Approve PTO Request","message":"Sarah Chen requesting 5 days off Mar 15-19.","actions":[{"id":"approve","label":"Approve"},{"id":"deny","label":"Deny"}]}'
```

### Run

```bash
cd apps/mobile-exec/mobile-exec-fixed
npx expo start --clear
```

If 8081 is in use, Expo will prompt to use 8082.


### Note-

w — opens the app in your web browser at localhost:8081
r — reloads the app (clears in-memory state like the decision cards, re-fetches all JS)

---

## 8️⃣ Common Issues & Troubleshooting

### ❗ Invalid supabaseUrl

If you see:

```
Invalid supabaseUrl: Must be a valid HTTP or HTTPS URL
```

You likely have placeholder values in `.env.local`.

Replace:

```env
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
```

With your actual project URL:

```env
NEXT_PUBLIC_SUPABASE_URL=https://xxxxxxxx.supabase.co
```

Then restart the dev server.

---

### 💡 EMFILE: too many open files (Expo)

Run:

```bash
ulimit -n 65536
```

Then restart Expo.

---

### ⚠ Backend 500 Errors / Missing Tables

If you see:

```
relation "onboarding_packets" does not exist
```

Run migrations:

```bash
docker compose exec backend alembic upgrade head
```

---

## 9️⃣ Port Quick Reference

| Service        | Port  |
|----------------|-------|
| Postgres       | 5432  |
| Backend API    | 8000  |
| Web Employee   | 3000  |
| Web Employer   | 3001  |
| Mobile         | 8081  |
| Mobile Exec    | 8082  |

---

## 🔟 Recommended Startup Order

1. `conda activate empower_llc`
2. `docker compose up --build`
3. Start Web Employee
4. Start Web Employer
5. Start Mobile
6. Start Mobile Exec

---

## 🎉 System Architecture

- **Clients (Web & Mobile)** → Connect to Backend API  
- **Backend API** → Writes to Postgres  
- **AI Orchestrator** → Communicates with Backend API  
- **Supabase** → Handles authentication for all frontend clients  