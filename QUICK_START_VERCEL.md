# 🚀 Quick Start: Deploy to Vercel (Right Now!)

## ⚡ Immediate Actions (5 minutes)

### 1. Push Code to GitHub (if not done)
```bash
cd /Users/harshitagarwal/Downloads/Match_analysis_engine_app
git add .
git commit -m "Ready for Vercel deployment"
git push
```

### 2. Configure Vercel Dashboard

Go to: **https://vercel.com/dashboard** → Your Project → **Settings**

#### A. Set Root Directory
- Settings → General → Root Directory
- Click "Edit" → Enter: `frontend` → Save

#### B. Set Build Settings
- Settings → General → Build & Development Settings
- **Build Command**: `npm run build`
- **Output Directory**: `dist`
- **Install Command**: `npm install` (or leave default)

### 3. Redeploy
- Go to **Deployments** tab
- Click **"..."** on latest deployment → **"Redeploy"**

## ✅ That's It!

Your app will be live at: `https://badminton-trial-app.vercel.app`

---

## 📋 What Vercel Needs to Know

| Setting | Value |
|---------|-------|
| **Root Directory** | `frontend` |
| **Build Command** | `npm run build` |
| **Output Directory** | `dist` |
| **Framework** | Vite (auto-detected) |

---

## 🔍 If Deployment Fails

1. **Check Build Logs**: Click on the failed deployment → See error messages
2. **Common Issues**:
   - ❌ Root Directory not set → Set to `frontend`
   - ❌ Build command wrong → Should be `npm run build`
   - ❌ Output directory wrong → Should be `dist`
   - ❌ Missing dependencies → Check `package.json` exists in `frontend/`

---

## 💡 Pro Tip

After first successful deployment, every `git push` will automatically deploy! 🎉

