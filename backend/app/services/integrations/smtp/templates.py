"""HTML-шаблоны писем «Глафира Рекрутёр».

`_email_shell` — общий каркас (хедер с брендом + подпись + футер), применяется ко
ВСЕМ письмам, чтобы они выглядели единообразно. `render_*` — конкретные письма.
Вёрстка table-based + inline-стили (email-клиенты не поддерживают внешний CSS/flex).
Пользовательские значения экранируются (html.escape). Письмо в UTF-8 (charset),
кириллица — как есть.
"""

import html as _html

LOGIN_URL = "https://glafira.dclouds.ru/login"


def _email_shell(content_html: str, preheader: str = "", company_name: str = "") -> str:
    """Оборачивает контент письма в общий хедер (бренд) + подпись + футер.

    company_name — компания ВАКАНСИИ (заказчик агентства или сам арендатор). Задан →
    шапка «Глафира · <Компания>» и подпись «Глафира — подбор персонала «<Компания>»».
    Пусто (служебные письма: доступ к аккаунту, тест SMTP) → прежний обезличенный
    бренд «Глафира Рекрутёр» / «Команда Глафира Рекрутёр».
    """
    pre = _html.escape(preheader)
    company = (company_name or "").strip()
    company_e = _html.escape(company)
    # Шапка: бренд + компания вакансии (если известна).
    brand_suffix = f"&nbsp;· {company_e}" if company else "&nbsp;Рекрутёр"
    # Подпись: с компанией — от лица подбора этой компании, иначе прежняя.
    signature = (
        f"Глафира — подбор персонала «{company_e}»" if company else "Команда Глафира Рекрутёр"
    )
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<meta http-equiv="X-UA-Compatible" content="IE=edge"/>
</head>
<body style="margin:0;padding:0;width:100%;background:#ECEFF2;-webkit-text-size-adjust:100%;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;height:0;width:0;">{pre}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#ECEFF2;">
  <tr><td align="center" style="padding:40px 16px;">
    <table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0" style="width:560px;max-width:560px;background:#FFFFFF;border-radius:16px;overflow:hidden;box-shadow:0 12px 32px rgba(15,22,32,.10);">
      <tr><td style="padding:28px 40px 26px;border-bottom:1px solid #ECEFF2;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
          <td style="width:32px;height:32px;border-radius:8px;background:#FFD2E8;background-image:linear-gradient(135deg,#FFD2E8 0%,#FFB1D6 100%);text-align:center;vertical-align:middle;font-size:19px;line-height:32px;">👩🏻</td>
          <td style="padding-left:10px;vertical-align:middle;">
            <span style="font-family:'Inter',Arial,sans-serif;font-size:16px;font-weight:700;letter-spacing:-0.01em;color:#0F1620;">Глафира</span>
            <span style="font-family:'Inter',Arial,sans-serif;font-size:16px;font-weight:500;letter-spacing:-0.01em;color:#9AA3AE;">{brand_suffix}</span>
          </td>
        </tr></table>
      </td></tr>
      {content_html}
      <tr><td style="padding:28px 40px 0;"><div style="border-top:1px solid #ECEFF2;height:1px;line-height:1px;font-size:0;">&nbsp;</div></td></tr>
      <tr><td style="padding:22px 40px 32px;">
        <p style="margin:0 0 3px;font-family:'Inter',Arial,sans-serif;font-size:14px;line-height:1.5;color:#3A4452;">С уважением,</p>
        <p style="margin:0;font-family:'Inter',Arial,sans-serif;font-size:14px;font-weight:600;line-height:1.5;color:#0F1620;">{signature}</p>
      </td></tr>
    </table>
    <table role="presentation" width="560" cellpadding="0" cellspacing="0" border="0" style="width:560px;max-width:560px;">
      <tr><td style="padding:22px 40px 8px;text-align:center;">
        <p style="margin:0;font-family:'Inter',Arial,sans-serif;font-size:12px;line-height:1.6;color:#9AA3AE;">Это письмо отправлено автоматически. Если вы не ожидали его, просто проигнорируйте.</p>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>"""


def _heading(text: str) -> str:
    return (
        "<h1 style=\"margin:0 0 18px;font-family:'Inter',Arial,sans-serif;font-size:22px;"
        "font-weight:600;line-height:1.3;letter-spacing:-0.01em;color:#0F1620;\">"
        f"{_html.escape(text)}</h1>"
    )


def render_credentials_email(full_name: str, login: str, temp_password: str, login_url: str = LOGIN_URL) -> str:
    """Письмо с доступом к аккаунту (логин + временный пароль)."""
    login_e = _html.escape(login or "")
    pw = _html.escape(temp_password or "")
    url = _html.escape(login_url or LOGIN_URL)
    content = f"""
      <tr><td style="padding:34px 40px 8px;">
        {_heading(f'Здравствуйте, {full_name or ""}!')}
        <p style="margin:0 0 8px;font-family:'Inter',Arial,sans-serif;font-size:15px;line-height:1.6;color:#3A4452;">Для вас создан аккаунт в системе <strong style="color:#0F1620;font-weight:600;">Глафира&nbsp;Рекрутёр</strong>. Используйте данные ниже, чтобы войти.</p>
      </td></tr>
      <tr><td style="padding:18px 40px 8px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F8F9FB;border:1px solid #ECEFF2;border-radius:12px;">
          <tr><td style="padding:22px 24px 6px;"><div style="font-family:'Inter',Arial,sans-serif;font-size:11px;font-weight:500;letter-spacing:0.04em;text-transform:uppercase;color:#9AA3AE;margin-bottom:14px;">Данные для входа</div></td></tr>
          <tr><td style="padding:0 24px 14px;">
            <div style="font-family:'Inter',Arial,sans-serif;font-size:12px;color:#5B6573;margin-bottom:5px;">Логин</div>
            <div style="font-family:'JetBrains Mono',Menlo,Consolas,monospace;font-size:14px;font-weight:500;color:#0F1620;background:#FFFFFF;border:1px solid #E6E9EC;border-radius:8px;padding:11px 14px;word-break:break-all;">{login_e}</div>
          </td></tr>
          <tr><td style="padding:0 24px 22px;">
            <div style="font-family:'Inter',Arial,sans-serif;font-size:12px;color:#5B6573;margin-bottom:5px;">Пароль</div>
            <div style="font-family:'JetBrains Mono',Menlo,Consolas,monospace;font-size:14px;font-weight:500;color:#0F1620;background:#FFFFFF;border:1px solid #E6E9EC;border-radius:8px;padding:11px 14px;letter-spacing:0.01em;word-break:break-all;">{pw}</div>
          </td></tr>
        </table>
      </td></tr>
      <tr><td align="center" style="padding:18px 40px 6px;">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center"><tr>
          <td style="border-radius:8px;background:#2A8AF0;"><a href="{url}" target="_blank" style="display:inline-block;font-family:'Inter',Arial,sans-serif;font-size:15px;font-weight:600;color:#FFFFFF;padding:13px 26px;border-radius:8px;">Войти в систему</a></td>
        </tr></table>
      </td></tr>
      <tr><td style="padding:20px 40px 4px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
          <td style="width:4px;background:#E0A21A;border-radius:4px;">&nbsp;</td>
          <td style="padding-left:14px;"><p style="margin:0;font-family:'Inter',Arial,sans-serif;font-size:13px;line-height:1.55;color:#5B6573;">Рекомендуем сменить пароль после первого входа в систему.</p></td>
        </tr></table>
      </td></tr>
    """
    return _email_shell(content, preheader="Для вас создан аккаунт в системе Глафира Рекрутёр. Данные для входа внутри.")


def render_simple_email(
    heading: str, body_html: str, preheader: str = "", company_name: str = ""
) -> str:
    """Универсальное письмо: заголовок + произвольный HTML-контент кода.

    body_html — внутренний HTML (формируется кодом, НЕ пользовательский ввод).
    company_name — компания вакансии для шапки/подписи (см. `_email_shell`).
    Служебные письма (не про конкретную вакансию) компанию НЕ передают.
    """
    content = f"""
      <tr><td style="padding:34px 40px 8px;">
        {_heading(heading)}
        <div style="font-family:'Inter',Arial,sans-serif;font-size:15px;line-height:1.6;color:#3A4452;">{body_html}</div>
      </td></tr>
    """
    return _email_shell(content, preheader=preheader or heading, company_name=company_name)
