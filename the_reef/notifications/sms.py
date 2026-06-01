"""SMS notifications via Gmail SMTP → Verizon email-to-SMS gateway.

Required env vars:
  SMTP_USERNAME   Gmail address (e.g. yourname@gmail.com)
  SMTP_PASSWORD   Gmail App Password (not your login password)
  SMS_RECIPIENT   Verizon gateway address (e.g. 7208399656@vtext.com)
"""
from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText


def send_sms(subject: str, body: str) -> bool:
    username = os.environ.get("SMTP_USERNAME")
    password = os.environ.get("SMTP_PASSWORD")
    recipient = os.environ.get("SMS_RECIPIENT")

    if not all([username, password, recipient]):
        print("[sms] SMTP credentials not configured — skipping notification")
        return False

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = username
    msg["To"] = recipient

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(msg)
        print(f"[sms] Sent: {subject}")
        return True
    except Exception as e:
        print(f"[sms] Failed to send: {e}")
        return False


def trade_alert(ticker: str, shares: int, price: float, stop: float, target: float, conviction: int, cash_remaining: float):
    subject = "REEF BUY"
    body = (
        f"BUY {shares} {ticker} @ ${price:.2f}\n"
        f"Stop ${stop:.2f} | Target ${target:.2f}\n"
        f"Conviction {conviction}/10\n"
        f"Cash left: ${cash_remaining:,.0f}"
    )
    send_sms(subject, body)


def daily_digest(portfolio_value: float, pnl: float, pnl_pct: float, positions: dict, cash: float):
    subject = "REEF DAILY"
    pnl_str = f"+${pnl:.0f}" if pnl >= 0 else f"-${abs(pnl):.0f}"
    lines = [f"${portfolio_value:,.0f} ({pnl_str} {pnl_pct:+.1f}%)"]
    for ticker, pos in list(positions.items())[:3]:
        lines.append(f"{ticker} {pos.shares}sh {pos.unrealized_pnl_pct:+.1f}%")
    lines.append(f"Cash: ${cash:,.0f}")
    send_sms(subject, "\n".join(lines))
