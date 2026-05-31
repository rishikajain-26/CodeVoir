import os

css_path = r"C:\Users\Mridu\Desktop\coachin_fin\CodeVoir\frontend\src\index.css"

new_css = """
.codevoir-welcome-page,
.codevoir-dashboard-page {
  --cv-ink: #0a192f;
  --cv-blue: #0a66c2;
  --cv-blue-soft: #70b5f9;
  --cv-yellow: #ffc000;
  --cv-card: rgba(255, 255, 255, 0.75);
  --cv-line: rgba(10, 102, 194, 0.1);
}

.codevoir-welcome-page {
  background:
    radial-gradient(circle at 10% 20%, rgba(10, 102, 194, 0.08) 0%, transparent 45%),
    radial-gradient(circle at 90% 80%, rgba(112, 181, 249, 0.12) 0%, transparent 50%),
    radial-gradient(circle at 50% 50%, rgba(255, 192, 0, 0.04) 0%, transparent 50%),
    linear-gradient(135deg, #f5f7fa 0%, #e4e9f0 100%);
  color: var(--cv-ink);
  overflow-x: hidden;
}

.codevoir-welcome-page::before,
.codevoir-dashboard-page::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(10, 102, 194, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(10, 102, 194, 0.02) 1px, transparent 1px);
  background-size: 40px 40px;
  mask-image: radial-gradient(circle at 50% 50%, black, transparent 85%);
}

.codevoir-welcome-page h1 {
  background: linear-gradient(92deg, #0a192f 0%, #004182 50%, #0a66c2 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  font-weight: 800;
  animation: welcome-slide-up 0.8s cubic-bezier(0.16, 1, 0.3, 1);
}

.codevoir-welcome-page h1 .text-amber-300 {
  background: linear-gradient(92deg, #0a66c2 0%, #3b82f6 50%, #00a3ff 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  text-shadow: none;
}

.codevoir-welcome-page p,
.codevoir-welcome-page .text-slate-300,
.codevoir-welcome-page .text-slate-400 {
  color: #475569;
  font-weight: 500;
}

.codevoir-welcome-page .dashboard-glass {
  border: 1px solid rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(16px);
  box-shadow: 
    0 10px 30px rgba(10, 25, 47, 0.03),
    0 1px 0 rgba(255, 255, 255, 0.8) inset;
  border-radius: 16px;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  animation: welcome-slide-up 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.1s both;
}

.codevoir-welcome-page .dashboard-glass:nth-child(1) {
  border-top: 3px solid #0a66c2;
}

.codevoir-welcome-page .dashboard-glass:nth-child(2) {
  border-top: 3px solid #ffc000;
}

.codevoir-welcome-page .dashboard-glass:hover {
  transform: translateY(-4px);
  border-color: rgba(10, 102, 194, 0.25);
  box-shadow: 
    0 15px 35px rgba(10, 25, 47, 0.06),
    0 1px 0 rgba(255, 255, 255, 0.8) inset;
}

.codevoir-welcome-page .text-white,
.codevoir-welcome-page .font-semibold.text-white {
  color: #0a192f;
}

.codevoir-welcome-page .text-amber-200 {
  color: #0a66c2;
}

.codevoir-welcome-page .welcome-signin-panel button {
  border: none;
  background: linear-gradient(135deg, #0a192f, #1e3a61);
  color: #ffffff;
  border-radius: 9999px;
  padding: 16px 32px;
  font-weight: 700;
  box-shadow: 0 4px 14px rgba(10, 25, 47, 0.2);
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  animation: welcome-slide-up 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.2s both;
}

.codevoir-welcome-page .welcome-signin-panel button:hover {
  background: linear-gradient(135deg, #0a66c2, #1b85e7);
  border: 2px solid #ffc000;
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(10, 102, 194, 0.3);
}

.codevoir-welcome-page .dashboard-globe-panel::before,
.codevoir-dashboard-page .dashboard-globe-panel::before {
  inset: 8% 0 8% 4%;
  background:
    radial-gradient(circle at 50% 48%, rgba(10, 102, 194, 0.06), transparent 60%);
  filter: blur(6px);
}

.codevoir-welcome-page .logo-system,
.codevoir-dashboard-page .logo-system {
  inset: 0 5%;
}

.codevoir-welcome-page .logo-system::before,
.codevoir-dashboard-page .logo-system::before {
  display: none;
}

.codevoir-welcome-page .logo-orbit-ring-1,
.codevoir-dashboard-page .logo-orbit-ring-1 {
  width: 255px;
  height: 255px;
  border-color: rgba(10, 102, 194, 0.06);
}

.codevoir-welcome-page .logo-orbit-ring-2,
.codevoir-dashboard-page .logo-orbit-ring-2 {
  width: 360px;
  height: 360px;
  border-color: rgba(10, 102, 194, 0.06);
}

.codevoir-welcome-page .logo-orbit-ring-3,
.codevoir-dashboard-page .logo-orbit-ring-3 {
  width: 465px;
  height: 465px;
  border-color: rgba(10, 102, 194, 0.06);
}

.codevoir-welcome-page .logo-orbit-ring,
.codevoir-dashboard-page .logo-orbit-ring {
  box-shadow: none;
}

.codevoir-welcome-page .orbit-a,
.codevoir-dashboard-page .orbit-a {
  width: 260px;
  height: 260px;
}

.codevoir-welcome-page .orbit-b,
.codevoir-dashboard-page .orbit-b {
  width: 365px;
  height: 365px;
}

.codevoir-welcome-page .orbit-c,
.codevoir-dashboard-page .orbit-c {
  width: 470px;
  height: 470px;
}

.codevoir-welcome-page .cv-sun,
.codevoir-dashboard-page .cv-sun {
  background: radial-gradient(circle at 30% 30%, rgba(255, 255, 255, 0.15), transparent), radial-gradient(circle at 48% 44%, #0a192f, #020617 80%);
  border: 4px solid #ffffff;
  box-shadow: 0 8px 24px rgba(10, 25, 47, 0.15);
}

.cv-letters {
  color: #ffffff;
  font-family: "Space Grotesk", Inter, sans-serif;
  font-size: 74px;
  font-weight: 800;
  text-shadow: none;
}

.codevoir-welcome-page .cv-swoosh-blue,
.codevoir-dashboard-page .cv-swoosh-blue {
  border-color: #0a66c2 #0a66c2 transparent transparent;
  filter: none;
}

.codevoir-welcome-page .company-planet,
.codevoir-dashboard-page .company-planet {
  border: 1px solid rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.05);
  border-radius: 9999px;
  transition: transform 0.2s ease;
}

.codevoir-welcome-page .company-planet:hover,
.codevoir-dashboard-page .company-planet:hover {
  transform: scale(1.1) rotate(0deg);
  border-color: #0a66c2;
  box-shadow: 0 6px 14px rgba(10, 102, 194, 0.12);
}

.codevoir-welcome-page .company-logo-mark,
.codevoir-dashboard-page .company-logo-mark {
  background: #f1f5f9;
  color: #0a192f;
}

.codevoir-dashboard-page {
  background:
    radial-gradient(circle at 80% 15%, rgba(10, 102, 194, 0.18) 0%, transparent 45%),
    radial-gradient(circle at 20% 85%, rgba(112, 181, 249, 0.14) 0%, transparent 50%),
    radial-gradient(circle at 50% 50%, rgba(255, 192, 0, 0.06) 0%, transparent 50%),
    linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  color: var(--cv-ink);
}

.codevoir-dashboard-page header {
  border-bottom: 1px solid rgba(10, 102, 194, 0.1);
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.03);
}

.codevoir-dashboard-page header .h-16 {
  height: 52px;
}

.codevoir-dashboard-page > section {
  padding-top: 64px;
}

/* Ensure Dashboard Hero uses the light glassmorphic card style */
.codevoir-dashboard-page .dashboard-hero {
  border: 1px solid rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(20px) saturate(120%);
  box-shadow: 
    0 10px 30px rgba(10, 25, 47, 0.03),
    0 1px 0 rgba(255, 255, 255, 0.8) inset;
  border-radius: 24px;
  padding: 40px;
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  align-items: center;
  gap: 30px;
  overflow: hidden;
  animation: welcome-slide-up 0.8s cubic-bezier(0.16, 1, 0.3, 1);
}

.codevoir-dashboard-page .dashboard-hero h2 {
  background: linear-gradient(92deg, #0a192f 0%, #004182 50%, #0a66c2 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent !important;
  font-weight: 800;
  text-shadow: none;
}

.codevoir-dashboard-page .dashboard-hero p,
.codevoir-dashboard-page .dashboard-hero .text-slate-300 {
  color: #475569 !important;
  font-weight: 500;
}

.codevoir-dashboard-page .dashboard-hero .logo-orbit-ring {
  border-color: rgba(10, 102, 194, 0.06) !important;
}

.codevoir-dashboard-page .dashboard-hero .cv-sun {
  border-color: #ffffff;
}

.codevoir-dashboard-page .dashboard-glass,
.codevoir-dashboard-page .profile-side-panel {
  border: 1px solid rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.75);
  backdrop-filter: blur(20px) saturate(120%);
  box-shadow: 
    0 10px 30px rgba(10, 25, 47, 0.03),
    0 1px 0 rgba(255, 255, 255, 0.8) inset;
  border-radius: 16px;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

.codevoir-dashboard-page .border-l-amber-400 {
  border-left: none !important;
  border-top: 4px solid #ffc000 !important;
}

.codevoir-dashboard-page .dashboard-glass:hover {
  transform: translateY(-4px);
  border-color: rgba(10, 102, 194, 0.2);
  box-shadow: 
    0 15px 35px rgba(10, 25, 47, 0.05),
    0 1px 0 rgba(255, 255, 255, 0.8) inset;
}

.codevoir-dashboard-page h1,
.codevoir-dashboard-page h2,
.codevoir-dashboard-page .text-white,
.codevoir-dashboard-page .text-slate-100,
.codevoir-dashboard-page .font-semibold.text-white {
  color: #0a192f;
}

.codevoir-dashboard-page p,
.codevoir-dashboard-page .text-slate-300,
.codevoir-dashboard-page .text-slate-400,
.codevoir-dashboard-page .text-slate-500 {
  color: #475569;
  font-weight: 500;
}

.codevoir-dashboard-page .text-xs.uppercase,
.codevoir-dashboard-page .flex.items-center.gap-2.text-xs.uppercase {
  color: #0a66c2;
  font-weight: 700;
  letter-spacing: 0.18em;
}

.codevoir-dashboard-page .dashboard-primary-action {
  border: 2px solid #0a66c2;
  background: #0a66c2;
  color: #ffffff !important;
  border-radius: 9999px;
  font-weight: 700;
  box-shadow: 0 4px 12px rgba(10, 102, 194, 0.15);
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

.codevoir-dashboard-page .dashboard-primary-action:hover {
  background: #ffffff;
  color: #0a66c2 !important;
  border-color: #ffc000;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(10, 102, 194, 0.15);
}

.codevoir-dashboard-page .dashboard-secondary-action {
  border: 1px solid rgba(10, 102, 194, 0.15);
  background: rgba(255, 255, 255, 0.8);
  color: #0a66c2 !important;
  border-radius: 9999px;
  font-weight: 700;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.02);
  transition: all 0.2s ease;
}

.codevoir-dashboard-page .dashboard-secondary-action:hover {
  border-color: #ffc000;
  background: #ffffff;
  color: #004182 !important;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(255, 192, 0, 0.12);
}

.codevoir-dashboard-page header button {
  border: 1px solid rgba(10, 102, 194, 0.15);
  background: #ffffff;
  color: #0a192f;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.codevoir-dashboard-page header button:hover {
  border-color: #0a66c2;
  background: #f1f5f9;
}

.codevoir-dashboard-page .profile-drawer-trigger {
  position: fixed;
  left: 24px;
  top: 8px;
  z-index: 50;
  width: 36px;
  height: 36px;
  border: 1px solid rgba(10, 102, 194, 0.15);
  background: #ffffff;
  color: #0a192f;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transition: all 0.2s ease;
}

.codevoir-dashboard-page .profile-drawer-trigger:hover {
  border-color: #ffc000;
  background: #f1f5f9;
  color: #0a66c2;
  transform: scale(1.03);
}

.codevoir-dashboard-page .rounded.border.border-white\/10.bg-slate-950\/45 {
  border: 1px solid rgba(10, 102, 194, 0.1);
  background: rgba(255, 255, 255, 0.8);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.02);
  transition: all 0.2s ease;
}

.codevoir-dashboard-page .rounded.border.border-white\/10.bg-slate-950\/45:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 14px rgba(0, 0, 0, 0.04);
}

/* Metric card backgrounds customized for each parameter! */
.codevoir-dashboard-page .rounded.border.border-white\/10.bg-slate-950\/45:nth-child(1) {
  background: linear-gradient(135deg, rgba(10, 102, 194, 0.06), #ffffff);
  border-color: rgba(10, 102, 194, 0.15);
}

.codevoir-dashboard-page .rounded.border.border-white\/10.bg-slate-950\/45:nth-child(2) {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.06), #ffffff);
  border-color: rgba(16, 185, 129, 0.15);
}

.codevoir-dashboard-page .rounded.border.border-white\/10.bg-slate-950\/45:nth-child(3) {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.06), #ffffff);
  border-color: rgba(99, 102, 241, 0.15);
}

.codevoir-dashboard-page .rounded.border.border-white\/10.bg-slate-950\/45:nth-child(4) {
  background: linear-gradient(135deg, rgba(112, 181, 249, 0.08), #ffffff);
  border-color: rgba(112, 181, 249, 0.2);
}

.codevoir-dashboard-page .rounded.border.border-white\/10.bg-slate-950\/45:nth-child(5) {
  background: linear-gradient(135deg, rgba(255, 192, 0, 0.08), #ffffff);
  border-color: rgba(255, 192, 0, 0.2);
}

.codevoir-dashboard-page .round-shortcut-amber {
  border-top: 3px solid #ffc000;
  background: linear-gradient(135deg, rgba(255, 192, 0, 0.04), #ffffff);
}

.codevoir-dashboard-page .round-shortcut-amber:hover {
  border-color: #ffc000;
  background: rgba(255, 192, 0, 0.08);
  box-shadow: 0 8px 20px rgba(255, 192, 0, 0.12);
  transform: translateY(-2px);
}

.codevoir-dashboard-page .round-shortcut-teal {
  border-top: 3px solid #00a3ff;
  background: linear-gradient(135deg, rgba(0, 163, 255, 0.04), #ffffff);
}

.codevoir-dashboard-page .round-shortcut-teal:hover {
  border-color: #00a3ff;
  background: rgba(0, 163, 255, 0.08);
  box-shadow: 0 8px 20px rgba(0, 163, 255, 0.12);
  transform: translateY(-2px);
}

.codevoir-dashboard-page .round-shortcut-purple {
  border-top: 3px solid #8b5cf6;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.04), #ffffff);
}

.codevoir-dashboard-page .round-shortcut-purple:hover {
  border-color: #8b5cf6;
  background: rgba(139, 92, 246, 0.08);
  box-shadow: 0 8px 20px rgba(139, 92, 246, 0.12);
  transform: translateY(-2px);
}

@keyframes welcome-slide-up {
  from {
    opacity: 0;
    transform: translateY(18px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes dashboard-breathe {
  0%, 100% {
    border-color: rgba(10, 102, 194, 0.1);
  }
  50% {
    border-color: #ffc000;
  }
}

@media (max-width: 760px) {
  .dashboard-shell header .h-16 {
    height: auto;
    padding-top: 12px;
    padding-bottom: 12px;
    align-items: flex-start;
  }

  .dashboard-shell header .flex-wrap {
    width: 100%;
  }
}

@media (max-width: 1024px) {
  .dashboard-hero {
    min-height: auto;
    grid-template-columns: 1fr;
    padding-top: 34px;
    padding: 30px;
  }

  .dashboard-globe-panel {
    min-height: 360px;
  }

  .dashboard-workspace {
    grid-template-columns: 1fr;
  }

  .profile-drawer-panel {
    position: fixed;
    left: 12px;
    top: 78px;
    width: min(460px, calc(100vw - 24px));
  }

  .profile-drawer-trigger {
    left: 12px;
    top: 78px;
  }
}

* {
  box-sizing: border-box;
}

input,
select {
  width: 100%;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #ffffff;
  color: #0a192f;
  padding: 10px 14px;
  outline: none;
  transition: all 0.2s ease;
}

input:focus,
select:focus {
  border-color: #0a66c2;
  box-shadow: 0 0 0 3px rgba(10, 102, 194, 0.15);
}

textarea {
  color: #f8fafc;
}
"""

with open(css_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

truncated_lines = lines[:835]

with open(css_path, "w", encoding="utf-8") as f:
    f.writelines(truncated_lines)
    f.write(new_css)

print("index.css updated successfully!")
