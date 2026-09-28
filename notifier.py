"""Email notification service for sending Indeed-style job alerts.
Supports Gmail, Outlook, custom SMTP with responsive HTML email digests.
"""
import html
import json
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(__file__)
PROFILE_PATH = os.path.join(BASE_DIR, "profile.json")


def get_smtp_config():
    """Retrieve SMTP configuration from environment variables and profile.json."""
    recipient = os.getenv("ALERT_RECIPIENT_EMAIL", "").strip()
    target_prof = PROFILE_PATH if os.path.exists(PROFILE_PATH) else os.path.join(BASE_DIR, "profile.example.json")
    if not recipient and os.path.exists(target_prof):
        try:
            with open(target_prof, "r", encoding="utf-8") as f:
                p = json.load(f)
                recipient = p.get("notification_email", "").strip()
        except Exception:
            pass

    return {
        "host": os.getenv("SMTP_HOST", "smtp.gmail.com").strip(),
        "port": int(os.getenv("SMTP_PORT", "587")),
        "user": os.getenv("SMTP_USER", "").strip() or os.getenv("SENDER_EMAIL", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", "").strip() or os.getenv("SMTP_APP_PASSWORD", "").strip(),
        "recipient": recipient,
        "enabled": os.getenv("EMAIL_ALERTS_ENABLED", "true").lower() in ("true", "1", "yes"),
        "min_score": int(os.getenv("ALERT_MIN_SCORE", "50")),
    }


def is_smtp_configured():
    """Check if valid sender and password exist for sending alerts."""
    cfg = get_smtp_config()
    return bool(cfg["user"] and cfg["password"] and cfg["recipient"])


def build_indeed_alert_html(jobs, profile, alert_date=None):
    """Generate a clean, high-conversion Indeed-style HTML email digest."""
    date_str = alert_date or datetime.now().strftime("%B %d, %Y")
    role_name = profile.get("base_role", "Full Stack Developer")
    user_name = profile.get("name", "Job Seeker")
    if user_name.lower() in ("your name", ""):
        user_name = "Candidate"

    job_cards_html = ""
    for j in jobs:
        title = html.escape(j.get("title") or "Software Engineer")
        company = html.escape(j.get("company") or "Tech Company")
        loc = html.escape(j.get("location") or "Remote")
        source = html.escape((j.get("source") or "web").upper())
        url = j.get("url") or "#"
        score = j.get("_score", 0)

        # Badge styling based on match strength
        if score >= 60:
            score_badge_bg = "#ecfdf5"
            score_badge_color = "#059669"
            score_label = f"★ {score}% Match · Strong Match"
        elif score >= 35:
            score_badge_bg = "#eff6ff"
            score_badge_color = "#2563eb"
            score_label = f"{score}% Match · Potential"
        else:
            score_badge_bg = "#f3f4f6"
            score_badge_color = "#4b5563"
            score_label = f"{score}% Match"

        # Matched skills chips
        matched_skills = j.get("_matched") or []
        chips_html = ""
        for s in matched_skills[:5]:
            chips_html += f'<span style="display:inline-block;background:#f3f4f6;color:#374151;font-size:11px;font-weight:600;padding:2px 8px;border-radius:4px;margin-right:4px;margin-bottom:4px;">{html.escape(s)}</span>'

        desc = j.get("description") or ""
        clean_desc = html.escape(desc[:220].strip()) + ("..." if len(desc) > 220 else "")

        job_cards_html += f"""
        <div style="background:#ffffff;border:1px solid #e5e7eb;border-radius:10px;padding:18px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
            <div style="margin-bottom:6px;">
                <span style="background:{score_badge_bg};color:{score_badge_color};font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:20px;display:inline-block;">{score_label}</span>
                <span style="float:right;background:#f9fafb;color:#6b7280;font-size:11px;font-weight:600;padding:2px 7px;border-radius:4px;border:1px solid #e5e7eb;">{source}</span>
            </div>
            <h3 style="margin:8px 0 3px 0;font-size:17px;line-height:1.3;color:#111827;">
                <a href="{url}" style="color:#0f52ba;text-decoration:none;font-weight:700;" target="_blank">{title}</a>
            </h3>
            <div style="font-size:14px;color:#374151;font-weight:600;margin-bottom:4px;">{company}</div>
            <div style="font-size:12.5px;color:#6b7280;margin-bottom:10px;">📍 {loc}</div>
            {f'<div style="font-size:13px;color:#4b5563;line-height:1.45;margin-bottom:12px;">{clean_desc}</div>' if clean_desc else ''}
            {f'<div style="margin-bottom:14px;">{chips_html}</div>' if chips_html else ''}
            <div>
                <a href="{url}" target="_blank" style="display:inline-block;background:#2557a7;color:#ffffff;font-size:13px;font-weight:700;padding:8px 18px;border-radius:6px;text-decoration:none;text-align:center;">Apply on Company Site →</a>
            </div>
        </div>
        """

    total_jobs = len(jobs)
    job_plural = "job" if total_jobs == 1 else "jobs"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>New Job Alert: {total_jobs} New {role_name} {job_plural.capitalize()}</title>
    </head>
    <body style="margin:0;padding:0;background-color:#f4f5f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#111827;">
        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color:#f4f5f8;padding:24px 12px;">
            <tr>
                <td align="center">
                    <table width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width:580px;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e5e7eb;">
                        <!-- Header banner -->
                        <tr>
                            <td style="background:#2557a7;padding:22px 24px;text-align:left;">
                                <div style="font-size:12px;font-weight:800;letter-spacing:1px;color:#93c5fd;text-transform:uppercase;margin-bottom:4px;">PERSONAL JOB RADAR · ALERT</div>
                                <h1 style="margin:0;font-size:22px;color:#ffffff;font-weight:800;line-height:1.25;">
                                    {total_jobs} new {role_name} {job_plural} found
                                </h1>
                                <div style="font-size:12.5px;color:#dbeafe;margin-top:4px;">{date_str} · Curated for {html.escape(user_name)}</div>
                            </td>
                        </tr>
                        <!-- Content -->
                        <tr>
                            <td style="padding:20px 22px;">
                                <p style="font-size:14px;color:#4b5563;margin-top:0;margin-bottom:18px;line-height:1.5;">
                                    Here are the latest matching jobs scraped from your configured sources (Welcome to the Jungle, YC, Himalayas, Remotive, RemoteOK, and JobSpy):
                                </p>
                                {job_cards_html}
                                <div style="text-align:center;padding:12px 0 6px 0;">
                                    <a href="http://localhost:8501" target="_blank" style="display:inline-block;background:#10b981;color:#ffffff;font-size:13.5px;font-weight:700;padding:10px 22px;border-radius:6px;text-decoration:none;">Open Full Job Matcher Dashboard ⚡</a>
                                </div>
                            </td>
                        </tr>
                        <!-- Footer -->
                        <tr>
                            <td style="background:#f9fafb;border-top:1px solid #e5e7eb;padding:16px 22px;text-align:center;font-size:11.5px;color:#9ca3af;line-height:1.4;">
                                Sent automatically by your personal 15-minute Job Scraper bot.<br>
                                You received this because email notifications are enabled.
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """
    return html_content


def send_email_message(subject, html_body, text_body=None, recipient=None):
    """Internal SMTP sender handling TLS connection and error handling."""
    cfg = get_smtp_config()
    to_email = recipient or cfg["recipient"]

    if not cfg["user"] or not cfg["password"]:
        return {
            "status": "error",
            "message": "SMTP credentials missing. Please set SMTP_USER and SMTP_PASSWORD in .env"
        }

    if not to_email:
        return {
            "status": "error",
            "message": "Recipient email not specified. Set ALERT_RECIPIENT_EMAIL in .env or enter in app."
        }

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Job Radar Alerts <{cfg['user']}>"
    msg["To"] = to_email

    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    else:
        # Fallback text summary
        fallback_text = f"{subject}\n\nPlease view this email in an HTML-compatible client.\nOpen Dashboard: http://localhost:8501"
        msg.attach(MIMEText(fallback_text, "plain", "utf-8"))

    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if cfg["port"] == 465:
            # SSL
            server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20)
        else:
            # TLS
            server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=20)
            server.ehlo()
            server.starttls()
            server.ehlo()

        server.login(cfg["user"], cfg["password"])
        server.sendmail(cfg["user"], [to_email], msg.as_string())
        server.quit()
        return {
            "status": "success",
            "message": f"Email successfully sent to {to_email}!"
        }
    except smtplib.SMTPAuthenticationError as auth_err:
        return {
            "status": "error",
            "message": f"SMTP Authentication failed. For Gmail, use a 16-character App Password (not your normal password): {auth_err}"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"SMTP sending error: {str(e)}"
        }


def send_job_alert_email(jobs, profile, recipient=None):
    """Format and send the Indeed-style job alert digest."""
    if not jobs:
        return {"status": "skipped", "message": "No jobs to alert"}

    cfg = get_smtp_config()
    if not cfg["enabled"]:
        return {"status": "skipped", "message": "Email alerts disabled in settings"}

    total = len(jobs)
    role = profile.get("base_role", "Developer")
    subject = f"🎯 Job Alert: {total} new {role} {'role' if total == 1 else 'roles'} for you"

    html_body = build_indeed_alert_html(jobs, profile)
    return send_email_message(subject, html_body, recipient=recipient)


def send_test_email(recipient=None):
    """Send an immediate test alert to verify user's SMTP setup."""
    cfg = get_smtp_config()
    to_email = recipient or cfg["recipient"]

    if not to_email:
        return {
            "status": "error",
            "message": "Please provide a valid recipient email address."
        }

    mock_profile = {
        "name": "Test User",
        "base_role": "Full Stack Developer",
    }
    mock_jobs = [
        {
            "title": "Full Stack Engineer (React / Node.js)",
            "company": "Stripe",
            "location": "Worldwide Remote",
            "source": "wttj",
            "url": "https://www.welcometothejungle.com",
            "_score": 95,
            "_matched": ["React", "Node.js", "TypeScript", "REST API", "Docker"],
            "description": "Building next-generation global financial infrastructure. Looking for strong Full Stack Developers with React and Node.js expertise."
        },
        {
            "title": "Frontend Developer (Next.js)",
            "company": "Vercel Partner Startup",
            "location": "Remote",
            "source": "himalayas",
            "url": "https://himalayas.app",
            "_score": 85,
            "_matched": ["Next.js", "React", "TypeScript", "Tailwind"],
            "description": "Fast-paced startup creating AI-powered web developer tooling. Remote-first culture with flexible hours."
        }
    ]

    subject = "🎯 Test Job Alert: Your Email Notifications Are Working!"
    html_body = build_indeed_alert_html(mock_jobs, mock_profile)
    return send_email_message(subject, html_body, recipient=to_email)
