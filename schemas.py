from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, field_validator


class AdminSchema(BaseModel):
    username: str
    password: str
    email: EmailStr
    full_name: str


class SetupSchema(BaseModel):
    cml_workspace_domain: str
    cml_api_key: str
    cml_namespace_prefix: str
    cml_kubeconfig_content: str

    ldap_enabled: bool = False
    ldap_server: str = ""
    ldap_port: Optional[int] = Field(None, ge=1, le=65535)
    ldap_base_dn: str = ""
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""

    alert_enabled: bool = False
    use_tls: bool = True
    # Made these optional with defaults so "Skip" doesn't fail validation
    smtp_server: str = ""
    smtp_port: Optional[int] = Field(587, ge=1, le=65535) 
    smtp_user: str = ""
    smtp_password: str = ""
    sender_email: Optional[EmailStr] = None


class LDAPSchema(BaseModel):
    ldap_enabled: bool
    server: str = ""
    port: Optional[int] = Field(None, ge=1, le=65535)
    base_dn: str = ""
    bind_dn: str = ""
    bind_password: str = ""


class CMLSchema(BaseModel):
    workspace_domain: str
    api_key: str
    namespace_prefix: str
    kubeconfig_content: Optional[str] = None


class AlertsSchema(BaseModel):
    alert_enabled: bool
    use_tls: bool

    smtp_server: str = Field(min_length=1)
    smtp_port: int = Field(ge=1, le=65535) 
    smtp_user: str = Field(min_length=1)
    smtp_password: str = ""
    alert_subject: str = Field(min_length=1)
    report_subject: str = Field(min_length=1)

    sender_email: EmailStr

    alert_recipient_emails: List[EmailStr] = Field(min_length=1)
    report_recipient_emails: List[EmailStr] = Field(min_length=1)

    alert_cron: str = ""
    report_cron: str = ""

    # --- Custom Validators ---
    @field_validator('alert_recipient_emails', 'report_recipient_emails', mode='before')
    @classmethod
    def parse_emails(cls, value):
        if not value:
            return []
        if isinstance(value, str):
            return [email.strip() for email in value.split(',') if email.strip()]
        return value

    @field_validator('alert_cron', 'report_cron')
    @classmethod
    def validate_cron(cls, value):
        if value and len(value.strip().split()) != 5:
            raise ValueError("Cron schedule must have exactly 5 parts separated by spaces.")
        return value.strip()
