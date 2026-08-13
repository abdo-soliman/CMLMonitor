import logging
from flask import Flask
from models import Config
from extensions import db, app
from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.core.exceptions import LDAPBindError, LDAPException


def is_ldap_enabled():
    """
    Checks if LDAP is enabled in the database.

    Params:
    Returns: ldap_enabled -> bool, True if ldap.enabled is set to '1' in the configs table
    """
    with app.app_context():
        ldap_config = Config.query.filter_by(attr='ldap.enabled').first()
        return ldap_config and ldap_config.value.strip() == '1'


def validate_ldap_search(server_url: str, port: int, base_dn: str, bind_dn: str, bind_pass: str, test_username: str):
    """
    Test LDAP Connection by doing an LDAP search on a username provided by user

    Params: server_url -> str
            port -> int
            base_dn -> str
            bind_pass -> str
            test_username -> str
    Returns: ldap_test_successful -> bool, True if connection to LDAP server is successfully established
             message -> str, test connection result message
    """
    try:
        # 1. Connect and Bind to the LDAP Server
        server = Server(server_url, port=port, get_info=ALL)
        conn = Connection(server, user=bind_dn, password=bind_pass, auto_bind=True)

        # 2. Search for the test user
        # Using a combined filter to catch both Active Directory (sAMAccountName) and OpenLDAP (uid)
        search_filter = f"(|(sAMAccountName={test_username})(uid={test_username}))"

        conn.search(
            search_base=base_dn,
            search_filter=search_filter,
            search_scope=SUBTREE
        )

        if len(conn.entries) > 0:
            return True, "LDAP Test Was Successful"

        return False, f"Connected successfully, but test user '{test_username}' was not found in the Base DN."

    except LDAPBindError:
        return False, "LDAP Bind Failed: Invalid bind credentials."
    except LDAPException as e:
        return False, f"LDAP Connection Error: {str(e)}"
    except Exception as e:
        return False, f"An unexpected error occurred: {str(e)}"


def authenticate_and_user_data(username, password):
    """
    Authenticates a user against AD using uid (or sAMAccountName) and returns their data.
    If Authenticated Return User data, if failed return None

    Params: username -> str
            password -> str
    Returns: user_data -> dict or None, user_data dict = { 'uid': sAMAccountName, '', 'mail': mail, 'displayName': displayName }
    """

    with app.app_context():
        configs = Config.get_configs("ldap")
    
        server = Server(configs['LDAP_SERVER'], port=configs['LDAP_PORT'], get_info=ALL)
    
        try:
            # Step 1: Bind with the service account to search for the user
            service_conn = Connection(server, user=configs['BIND_USER_DN'], password=configs['BIND_USER_PASSWORD'], auto_bind=True)
    
            # Search for the user
            attributes = ['sAMAccountName', 'mail', 'displayName']
            search_filter = f"(&(objectclass=person)(sAMAccountName={username}))"
    
            service_conn.search(
                search_base=configs['BASE_DN'],
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=attributes
            )
    
            if not service_conn.entries:
                return None # User not found
    
            # TODO Replace uid with sAMAccountName
            entry = service_conn.entries[0]
            user_data = {
                "uid": str(entry.sAMAccountName),
                "mail": str(entry.mail),
                "displayName": str(entry.displayName)
            }
    
            # Extract the user's full DN
            user_dn = entry.entry_dn
    
            # Step 2: Attempt to bind as the actual user to verify their password
            user_conn = Connection(server, user=user_dn, password=password, auto_bind=True)
    
            # Unbind both connections if successful
            user_conn.unbind()
            service_conn.unbind()
    
            return user_data
    
        except LDAPBindError:
            return None # Invalid password
        except LDAPException as e:
            print(f"LDAP Error: {e}")
            return None


def get_user_full_name(username):
    """
    Fetch first and last name of an AD user by username (sAMAccountName)

    Params: username -> str, AD username (sAMAccountName)
    Returns: display_name -> str or None
    """

    with app.app_context():
        configs = Config.get_configs("ldap")

        try:
            server = Server(configs['LDAP_SERVER'], port=configs['LDAP_PORT'], get_info=ALL, connect_timeout=5)
    
            conn = Connection(server, user=configs['BIND_USER_DN'], password=configs['BIND_USER_PASSWORD'], auto_bind=True)
    
            search_filter = f"(&(objectClass=user)(sAMAccountName={username}))"
    
            conn.search(
                search_base=configs['BASE_DN'],
                search_filter=search_filter,
                attributes=["displayName"]
            )
    
            if conn.entries is None or len(conn.entries) == 0:
                conn.unbind()
                return None
    
            entry = conn.entries[0]
            display_name = entry.displayName.value
    
            conn.unbind()
            return display_name
        except Exception as e:
            logging.info(f"Connection to LDAP Server failed with error: {e}, ignoring user display name for user: {username}")
    
        return None
