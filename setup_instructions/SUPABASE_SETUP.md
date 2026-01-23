# Supabase Setup (Postgres) + First Admin Bootstrap

This project uses **Supabase as a hosted PostgreSQL database**.  
All user creation inside the app is **locked behind admin login**, so the **first admin account must be created directly in Supabase** (one-time bootstrap).

---

## 0) Prerequisites

- Supabase account + a new Supabase project
- Your repo cloned locally
- Python environment set up with your project dependencies
- **Zsh** shell

---

## 1) Create a Supabase Project

1. Create a new Supabase project
2. Note down:
   - **Database password** (important)
   - **Region** (choose closest)

---

## 2) Get the Correct Postgres Connection String

In Supabase:
- Go to **Project Settings → Database**
- Under connection strings, choose:
  - **Transaction pooler** (recommended for Streamlit / bursty apps)

You will see something like:

```
postgresql://postgres.<project_ref>:[YOUR_PWD]@aws-<region>.pooler.supabase.com:6543/postgres
```

### Important notes
- `[...]` are **placeholders** in the UI — do **not** include brackets unless your password literally contains them.
- If your password contains special characters (e.g. `@`, `:`, `[`, `]`, `#`), URL-encode it.
- Always include SSL:

✅ Final format:
```
postgresql://postgres.<project_ref>:<URL_ENCODED_PASSWORD>@aws-<region>.pooler.supabase.com:6543/postgres?sslmode=require
```

---

## 3) Configure Environment Variables

Create/update `.env`:

```env
# DB (Supabase)
DATABASE_URL=postgresql://postgres.<project_ref>:<URL_ENCODED_PASSWORD>@aws-<region>.pooler.supabase.com:6543/postgres?sslmode=require

# LLM
GEMINI_API_KEY=your_key

# Cookie auth signing secret
SESSION_SECRET=your_long_random_secret
```

---

## 4) Initialize DB Tables

Run your app locally and create tables using your existing admin/dev tools (if exposed), OR run your project’s init command/script if you have one.

If you already have `init_db()` wired in the UI, use it once.

After this step, Supabase should have tables like:
- `users`
- `categories`
- `user_category_access`
- `conversations`
- `message_traces`
(and any other app tables)

---

## 5) Bootstrap the First Admin (One-Time)

Because all account creation is locked behind admin access, the **first admin must be inserted manually**.

### 5.1 Generate the password hash (must match your app)

Your `users` table stores **password_hash**, not plaintext.

You can generate a hash for the password using this:

```zsh
python -c "from src.user_service import hash_password; print(hash_password('YOUR_ADMIN_PASSWORD'))"
```

If your function name differs, update accordingly.

---

### 5.2 Insert admin user via Supabase SQL Editor

In Supabase Dashboard:
- Go to **SQL Editor**
- Run this query (replace email + hash):

```sql
INSERT INTO users (
  email,
  password_hash,
  role,
  is_active,
  access_version,
  created_at
)
VALUES (
  'admin@gmail.com',
  '$2b$12$4esGBmIdDGjpHjHdHPbXIeEPyBcyAJbgKy0EJukeQIJD1MCZz8WFO',
  'admin',
  true,
  1,
  now()
);
```

This creates the first admin account.

---

## 6) Verify Admin Exists

Run in Supabase SQL Editor:

```sql
SELECT id, email, role, is_active, access_version
FROM users
ORDER BY created_at DESC;
```

Expected:
- Your admin row exists
- `role = 'admin'`
- `is_active = true`

---

## 7) Login & Create Analysts via Admin UI

Now that admin exists:
1. Launch the app
2. Login with the admin credentials you inserted
3. Use the Admin dashboard to:
   - create analyst accounts
   - assign category access
   - manage access versions

---

# Supabase Setup (Minimal Bootstrap)

This project uses **Supabase as a hosted PostgreSQL database**.

All user creation inside the app is **locked behind admin login**, so the **first admin account must be created manually** in Supabase.  
After that, **all remaining tables and users are created from the app UI**.

This file documents the **minimum required steps** to get the system running.

---

## 1) Create a Supabase Project

1. Create a new Supabase project
2. Save:
   - Database password
   - Project region

---

## 2) Get the Correct Postgres Connection String

In Supabase:
- Go to **Project Settings → Database**
- Copy the **Transaction Pooler** connection string

It looks like:

```
postgresql://postgres.<project_ref>:[YOUR_PWD]@aws-<region>.pooler.supabase.com:6543/postgres
```

### Important
- `[...]` are placeholders — **do not include brackets**
- If your password has special characters, URL‑encode it
- Always use SSL

Final format:

```
postgresql://postgres.<project_ref>:<URL_ENCODED_PASSWORD>@aws-<region>.pooler.supabase.com:6543/postgres?sslmode=require
```

---

## 3) Configure Environment Variables

Create `.env`:

```env
DATABASE_URL=postgresql://postgres.<project_ref>:<URL_ENCODED_PASSWORD>@aws-<region>.pooler.supabase.com:6543/postgres?sslmode=require
GEMINI_API_KEY=your_key
SESSION_SECRET=your_long_random_secret
```

---

## 4) Create ONLY the users table (minimum required)

Run this **once** in the Supabase SQL Editor:

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    access_version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);
```

No other tables are required at this stage.

---

## 5) Generate Admin Password Hash (local)

The app stores **hashed passwords only**.

Generate a hash using the app’s hashing logic:

```zsh
python -c "from src.user_service import hash_password; print(hash_password('YOUR_ADMIN_PASSWORD'))"
```

Copy the full output string.

---

## 6) Insert First Admin User (one-time)

In Supabase SQL Editor:

```sql
INSERT INTO users (
    email,
    password_hash,
    role,
    is_active,
    access_version,
    created_at
)
VALUES (
    'admin@gmail.com',
    '$2b$12$PASTE_HASH_FROM_STEP_5',
    'admin',
    true,
    1,
    now()
);
```

---

## 7) Login & Initialize Everything Else

1. Start the app:
   ```zsh
   streamlit run app/Analytics_Chat.py
   ```
2. Login with the admin credentials
3. Open **Admin / Developer Tools**
4. Click:
   - **Initialize DB tables**
   - **Ingest categories**

From this point forward:
- All remaining tables are created automatically
- All future users are created via the Admin UI
- No further manual SQL is required

---

## Notes

- The admin bootstrap is intentionally minimal and one‑time
- Re-running the users table creation is unnecessary
- This mirrors real production internal-tool bootstrapping patterns