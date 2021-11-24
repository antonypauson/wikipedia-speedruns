from flask.helpers import url_for
import pymysql
from werkzeug.utils import redirect
from util.decorators import check_user
from flask import session, request, render_template, Blueprint, current_app
import flask_dance.contrib.google as oauth_google
from flask_mail import Message

from db import get_db
from mail import mail
from tokens import (
    create_reset_token, 
    verify_reset_token, 
    create_confirm_token, 
    verify_confirm_token

)

from pymysql.cursors import DictCursor

import bcrypt
import hashlib

user_api = Blueprint("users", __name__, url_prefix="/api/users")

# Setup OAuth
google_bp = oauth_google.make_google_blueprint(redirect_url="/api/users/auth/google/check", 
    scope=[
        "https://www.googleapis.com/auth/userinfo.profile", 
        "https://www.googleapis.com/auth/userinfo.email", 
        "openid"
    ]
)
# Note, url_prefix overrides the entire user_api prefix, not sure if this will get changed
user_api.register_blueprint(google_bp, url_prefix="/api/users/auth")


def send_reset_email(id, email, hashed, url_root):
    token = create_reset_token(id, hashed)
    link = f"{url_root}reset/{id}/{token}"

    msg = Message("Reset Your Password - wikispeedruns.com",
      recipients=[email])

    msg.body = 'Hello,\n\nYou or someone else has requested that a new password '\
               'be generated for your account. If you made this request, then '\
               'please follow this link: ' + link
    # msg.html = render_template('email_reset.html', link=link) #TODO
    mail.send(msg)


def send_confirmation_email(id, email, url_root):
    token = create_confirm_token(id)
    link = url_root + "confirm/" + token

    msg = Message("Confirm your Email - Wikispeedruns.com", recipients=[email])

    msg.body = 'Hello,\n\nClick the following link to confirm your email ' + link
    # msg.html = render_template('email_confirmation.html', link=link) #TODO

    mail.send(msg)


def valid_username(username):
    valid_char = lambda c: (c.isalnum() or c == '-' or c == '_' or c == '.')
    return all(map(valid_char, username))


def login_session(user):
    session.clear()
    session["user_id"] = user["user_id"]
    session["username"] = user["username"]
    session["admin"] = user["admin"] != 0


def logout_session():
    # Logout from oauth if there is oauth
    if (google_bp.token):
        token = google_bp.token["access_token"]
        resp = oauth_google.google.post(
            "https://accounts.google.com/o/oauth2/revoke",
            params={"token": token},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        assert resp.ok, resp.text
        del google_bp.token  # Delete OAuth token from storage


    session.pop("user_id", None)
    session.pop("username", None)
    session.pop("admin", None)


@user_api.post("/create/oauth")
def create_user_oauth():
    """
    Example json input
    {
        "username" : "echoingsins"
    }
    """

    # We assume that the oauth service provides an email
    # TODO Save google account id?
    email = session["pending_oauth_creation"]
    username = request.json["username"]

    # Validate username
    if (not valid_username(username)):
        return "Invalid username", 400

    query = "INSERT INTO `users` (`username`, `email`, `email_confirmed`) VALUES (%s, %s, %s)"

    db = get_db()
    with get_db().cursor() as cursor:
        result = cursor.execute(query, (username, email, True))

        if (result == 0):
            return ("User {} already exists".format(username), 409)

        db.commit()

    return ("User {} added".format(username), 201)


@user_api.post("/create/email")
def create_user():
    """
    Example json input
    {
        "username" : "echoingsins"
        "email" : "echoingsins@gmail.com    
        "password" : "lmao"
    }
    """

    if not all([field in request.json for field in ["username", "email", "password"]]):
        return "Invalid request", 400

    username = request.json["username"]
    email = request.json["email"]
    password = request.json["password"].encode() # TODO ensure charset is good

    # Validate username
    if (not valid_username(username)):
        return "Invalid username", 400

    # Use SHA256 to allow for arbitrary length passwords
    hash = bcrypt.hashpw(hashlib.sha256(password).digest(), bcrypt.gensalt())
    query = "INSERT INTO `users` (`username`, `hash`, `email`, `email_confirmed`) VALUES (%s, %s, %s, %s)"
    get_id_query = "SELECT LAST_INSERT_ID()"

    db = get_db()
    with get_db().cursor() as cursor:

        try:
            cursor.execute(query, (username, hash, email, False))

            cursor.execute(get_id_query)
            (id,) = cursor.fetchone()
            
            send_confirmation_email(id, email, request.url_root)

            db.commit()

        except pymysql.error.IntegrityError:
            return ("User {} already exists".format(username), 409)

    return ("User {} ({}) added".format(username, id), 201)


@user_api.get("/auth/google/check")
def check_google_auth():
    resp = oauth_google.google.get("/oauth2/v1/userinfo")
    assert resp.ok, resp.text
    # TODO do something with google user id

    email = resp.json()["email"]
    query = "SELECT * from `users` WHERE `email`=%s"

    db = get_db()
    # Check if user exists, and either login or set session to create new account
    with get_db().cursor(cursor=DictCursor) as cursor:
        result = cursor.execute(query, (email))

        if (result == 0):
            session["pending_oauth_creation"] = email
        else:
            user = cursor.fetchone()
            login_session(user)

    return redirect("/")


@user_api.post("/login")
def login():
    """
    Example json input
    {
        "username" : "echoingsins"
        "password" : "lmao"
    }

    OR 

    {
        "email" : "echoingsins@gmail.com"
        "password" : "lmao"
    }
    """

    # Validate request and pull fields
    if ("email" in request.json):
        query = "SELECT * FROM `users` WHERE `email`= %s"
        login = request.json["email"]
    elif ("username" in request.json):
        query = "SELECT * FROM `users` WHERE `username`= %s"
        login = request.json["username"]
    else:
        return ("Username/email not in request", 400)

    if ("password" not in request.json):
        return ("Password not in request", 400)
    
    password = request.json["password"].encode()

    db = get_db()
    with db.cursor(DictCursor) as cursor:
        # Query for user and check password
        result = cursor.execute(query, (login, ))

        if (result == 0):
            return "Bad username or password", 401

        user = cursor.fetchone()
        hash = user["hash"].encode()

        if not bcrypt.checkpw(hashlib.sha256(password).digest(), hash):
            return "Bad username or password", 401

    # Add session
    login_session(user)

    return "Logged in", 200


@user_api.post("/logout")
def logout():
    logout_session()
    return "Logged out", 200


@user_api.post("/change_password")
@check_user
def change_password():
    '''
    Given the old password and a new one, change the password
    '''
    get_query = "SELECT hash FROM `users` WHERE `user_id`=%s"
    update_query = "UPDATE `users` SET `hash`=%s WHERE `user_id`=%s"

    if ("old_password" not in request.json or "new_password" not in request.json):
        return ("Password(s) not in request", 400)
    
    id = session["user_id"]
    old_password = request.json["old_password"].encode()
    new_password = request.json["new_password"].encode()

    db = get_db()
    with db.cursor() as cursor:
        # Query for user and check password
        result = cursor.execute(get_query, (id, ))

        # TODO , should be found

        (old_hash,) = cursor.fetchone()
        old_hash = old_hash.encode()
        
        if not bcrypt.checkpw(hashlib.sha256(old_password).digest(), old_hash):
            return "Incorrect password", 401

        new_hash = bcrypt.hashpw(hashlib.sha256(new_password).digest(), bcrypt.gensalt())

        cursor.execute(update_query, (new_hash, id))
        db.commit()

    return "Password Changed", 200



@user_api.post("/confirm_email_request")
@check_user
def confirm_email_request():
    '''
        Request another email token be sent in as a logged in user, i.e. from profile page
    '''
    id = session["user_id"]
    query = "SELECT `email` FROM `users` WHERE `user_id`=%s"
    
    db = get_db()
    with db.cursor() as cursor:
        result = cursor.execute(query, (id, ))
        (email,) = cursor.fetchone()
        # TODO throw error?

    send_confirmation_email(id, email, request.url_root)

    return "New confirmation email sent", 200

@user_api.post("/confirm_email")
def confirm_email():
    token = request.json["token"]
    id = verify_confirm_token(token)
    
    if (id is None):
        return ("Invalid email confirmation link, could be outdated", 400)
   
    query = "UPDATE `users` SET `email_confirmed` = 1 WHERE `user_id`=%s"

    db = get_db()
    with db.cursor() as cursor:
        result = cursor.execute(query, (id, ))
        db.commit()

        # TODO throw error if not right?

    return "Email Confirmed"

@user_api.post("/reset_password_request")
def reset_password_request():
    '''
    Request a password reset for a particular email. Will always return 200 as to not give away
    the existence of certain emails on the website
    '''

    email = request.json['email']

    query = "SELECT `user_id`, `hash` FROM `users` WHERE `email`=%s"
    
    db = get_db()
    with db.cursor() as cursor:
        res = cursor.execute(query, (email, ))
        (id, hash) = cursor.fetchone()

        if (res != 0):
            send_reset_email(id, email, hash, request.url_root)

    return f"If the account for {email} exists, an email has been sent with a reset link", 200



@user_api.post("/reset_password")
def reset_password():
    '''
    Given the user id, reset token and a new password, change the password
    '''
    get_query = "SELECT hash FROM `users` WHERE `user_id`=%s"
    update_query = "UPDATE `users` SET `hash`=%s WHERE `user_id`=%s"

    if not all([field in request.json for field in ["user_id", "password", "token"]]):
        return "Invalid request", 400
    
    id = request.json["user_id"]
    password = request.json["password"].encode()
    token = request.json["token"]


    db = get_db()
    with db.cursor() as cursor:
        # Query for user and use password to decode token
        result = cursor.execute(get_query, (id, ))

        if (result == 0):
            return "Invalid id", 400

        (old_hash, ) = cursor.fetchone()

        if (id != verify_reset_token(token, old_hash)):
            return "Invalid token", 400

        new_hash = bcrypt.hashpw(hashlib.sha256(password).digest(), bcrypt.gensalt())
        cursor.execute(update_query, (new_hash, id))
        # TODO check

        db.commit()

    return "Password Changed", 200

