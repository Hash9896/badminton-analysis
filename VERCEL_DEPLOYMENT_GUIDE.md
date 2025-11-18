# Step-by-Step Vercel Deployment Guide

## ✅ What You've Already Done
1. ✅ Created GitHub repo `badminton-trial-app` and made it public
2. ✅ Created Vercel account and connected GitHub
3. ✅ Connected the repo to Vercel
4. ✅ Hit the deploy button

## 📋 Next Steps

### Step 1: Push Your Code to GitHub

First, make sure all your code is pushed to your GitHub repository:

```bash
# Navigate to your project directory
cd /Users/harshitagarwal/Downloads/Match_analysis_engine_app

# Check git status
git status

# If you haven't initialized git yet, do:
git init
git add .
git commit -m "Initial commit for Vercel deployment"

# Add your GitHub remote (replace YOUR_USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR_USERNAME/badminton-trial-app.git

# Push to GitHub
git branch -M main
git push -u origin main
```

### Step 2: Configure Vercel Project Settings

After you hit deploy, Vercel might show an error or configuration screen. Here's what you need to configure:

1. **Go to your Vercel Dashboard** → Select your `badminton-trial-app` project
2. **Click on "Settings"** tab
3. **Go to "General"** section
4. **Configure the following:**

   - **Root Directory**: Set this to `frontend`
     - Click "Edit" next to Root Directory
     - Enter: `frontend`
     - Click "Save"

   - **Build & Development Settings**:
     - **Framework Preset**: Select "Vite" (or leave as "Other")
     - **Build Command**: `npm run build`
     - **Output Directory**: `dist`
     - **Install Command**: `npm install`

### Step 3: Environment Variables (Optional)

If your app needs to connect to a backend API, you'll need to set environment variables:

1. **In Vercel Dashboard** → Your Project → **Settings** → **Environment Variables**
2. **Add Variable** (if you have a backend):
   - **Name**: `VITE_BACKEND_URL`
   - **Value**: Your backend API URL (e.g., `https://your-backend.vercel.app` or your backend server URL)
   - **Environment**: Select all (Production, Preview, Development)
   - Click "Save"

   **Note**: If you don't have a backend deployed yet, you can skip this. The app will default to `http://localhost:8000` which won't work in production, but the rest of the app will still function.

### Step 4: Redeploy

After configuring the settings:

1. Go to **Deployments** tab in Vercel
2. Click the **"..."** menu on the latest deployment
3. Click **"Redeploy"**
   
   OR

   Simply push a new commit to trigger automatic deployment:
   ```bash
   git add .
   git commit -m "Configure for Vercel"
   git push
   ```

### Step 5: Verify Deployment

1. Wait for the deployment to complete (you'll see a green checkmark)
2. Click on the deployment to see the **"Visit"** button
3. Click **"Visit"** to open your live app!

## 🔧 Troubleshooting

### Issue: Build Fails
- **Check**: Make sure `package.json` exists in the `frontend` folder
- **Check**: Make sure all dependencies are listed in `package.json`
- **Solution**: Look at the build logs in Vercel to see the exact error

### Issue: 404 Errors on Routes
- **Check**: Make sure `frontend/vercel.json` exists with the rewrite rules (it already does!)
- The vercel.json should have:
  ```json
  {
    "rewrites": [
      { "source": "/(.*)", "destination": "/index.html" }
    ]
  }
  ```

### Issue: Assets Not Loading
- **Check**: Make sure the build output directory is set to `dist`
- **Check**: Make sure `vite.config.ts` doesn't have a custom `base` path

### Issue: Backend API Not Working
- The app uses `VITE_BACKEND_URL` environment variable
- If you haven't set it, the app will try to connect to `http://localhost:8000` which won't work
- Either:
  1. Deploy your backend separately and set `VITE_BACKEND_URL` in Vercel
  2. Or remove/disable the chat feature that uses the backend

## 📝 Quick Checklist

Before deploying, make sure:
- [ ] Code is pushed to GitHub
- [ ] Root Directory is set to `frontend` in Vercel
- [ ] Build Command is `npm run build`
- [ ] Output Directory is `dist`
- [ ] `frontend/vercel.json` exists (✅ it does!)
- [ ] Environment variables are set (if needed)

## 🎉 You're Done!

Once deployed, you'll get a URL like: `https://badminton-trial-app.vercel.app`

Every time you push to GitHub, Vercel will automatically redeploy your app!

