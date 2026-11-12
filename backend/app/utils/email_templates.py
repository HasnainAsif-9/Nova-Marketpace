"""Transactional email templates.

Each function returns (subject, text_body, html_body). The HTML is a simple
inline-styled layout — no external assets so it renders in any mail client.
For richer templates, move these to Jinja files under app/templates/email/.
"""


def _layout(title, name, body_html, footer_note=""):
    safe_name = (name or "there").replace("&", "&amp;").replace("<", "&lt;")
    note = f'<p style="color:#888;font-size:12px;margin-top:24px;">{footer_note}</p>' if footer_note else ""
    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f4f4f5;font-family:Arial,Helvetica,sans-serif;">
  <div style="max-width:560px;margin:24px auto;background:#ffffff;border-radius:8px;overflow:hidden;">
    <div style="background:#0d9488;padding:16px 24px;">
      <span style="color:#ffffff;font-size:18px;font-weight:bold;">{title}</span>
    </div>
    <div style="padding:24px;color:#333;font-size:14px;line-height:1.6;">
      <p>Hi {safe_name},</p>
      {body_html}
      {note}
    </div>
  </div>
</body></html>"""


def _button(url, label):
    return (f'<p style="margin:24px 0;"><a href="{url}" style="display:inline-block;'
            f'background:#0d9488;color:#ffffff;text-decoration:none;padding:12px 24px;'
            f'border-radius:6px;font-weight:bold;">{label}</a></p>'
            f'<p style="font-size:12px;color:#888;word-break:break-all;">Or paste this link: {url}</p>')


def verification_email(name, link):
    subject = "Verify your NovaMarket email"
    text = (f"Hi {name or 'there'},\n\n"
            f"Please verify your email address by opening this link:\n\n{link}\n\n"
            "The link expires in 24 hours. If you did not create an account, ignore this email.")
    html = _layout("Verify your email", name, _button(link, "Verify Email"),
                   "If the button doesn't work, use the link above. This link expires in 24 hours.")
    return subject, text, html


def password_reset_email(name, link):
    subject = "Reset your NovaMarket password"
    text = (f"Hi {name or 'there'},\n\n"
            f"We received a request to reset your password. Open this link to choose a new one:\n\n{link}\n\n"
            "The link expires in 1 hour. If you did not request this, ignore this email — your password is unchanged.")
    html = _layout("Reset your password", name, _button(link, "Reset Password"),
                   "If you didn't request this, you can safely ignore this email. The link expires in 1 hour.")
    return subject, text, html


def order_confirmation_email(name, order_number, total, currency_symbol, order_url):
    """TODO(email): wire into order creation flow once SMTP is configured."""
    subject = f"Order {order_number} confirmed"
    text = (f"Hi {name or 'there'},\n\n"
            f"Thanks for your order {order_number}. Total: {currency_symbol}{total}.\n\n"
            f"Track it here: {order_url}")
    html = _layout("Order confirmed", name,
                   f"<p>Thanks for your order <strong>{order_number}</strong>.</p>"
                   f"<p>Total: <strong>{currency_symbol}{total}</strong></p>"
                   + _button(order_url, "View Order"))
    return subject, text, html
