import logging
import smtplib
from os.path import basename
from email.mime.text import MIMEText
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

def send_email(
        smtp_server,
        smtp_port,
        smtp_use_tls,
        smtp_user,
        smtp_password,
        sender_email,
        subject,
        content,
        recipient_emails,
        attachments=None
    ):
    # Create message container
    msg = MIMEMultipart("alternative")
    msg["From"] = sender_email
    msg["To"] = ", ".join(recipient_emails)
    msg["Subject"] = subject

    # Attach HTML part
    msg.attach(MIMEText(content, "html", "utf-8"))

    # file attachments
    for attachment in attachments or []:
        with open(attachment, "rb") as f:
            part = MIMEApplication(f.read(), Name=basename(attachment))

        part['Content-Disposition'] = 'attachment; filename="%s"' % basename(attachment)
        msg.attach(part)

    # Send email via SMTP
    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        if smtp_use_tls:
            server.starttls()  # Secure the connection
        server.login(smtp_user, smtp_password)
        server.sendmail(sender_email, recipient_emails, msg.as_string())
        logging.info(f"Alert Email sent to the following recipients: {recipient_emails}")
    except Exception as e:
        logging.error(f"Error sending email: {e}")
    finally:
        server.quit()


def smtp_test_email(smtp_server, smtp_port, smtp_use_tls, smtp_user, smtp_password, sender_email, recipients):
    try:
        # 1. Connect to the SMTP server
        smtp = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
        smtp.ehlo()
        
        # 2. Start TLS if requested
        if smtp_use_tls:
            smtp.starttls()
            smtp.ehlo()
            
        # 3. Login if credentials are provided
        if smtp_user and smtp_password:
            smtp.login(smtp_user, smtp_password)

        
        # 4. Send test email if a recipient is provided
        if recipients:
            msg = EmailMessage()
            msg.set_content("This is an automated test email from the CMLMonitor Initial Setup Wizard. If you are receiving this, your SMTP configuration is correct.")
            msg['Subject'] = "CMLMonitor: SMTP Verification Test"
            msg['From'] = sender_email
            msg['To'] = ", ".join(recipients)

            smtp.send_message(msg)

        smtp.quit()
        return True, "SMTP Test Was Successful"
    except smtplib.SMTPAuthenticationError:
        return False, "Authentication failed: Invalid username or password."
    except smtplib.SMTPException as e:
        return False, f"SMTP Error: {str(e)}"
    except Exception as e:
        return False, f"Connection Error: {str(e)}"
