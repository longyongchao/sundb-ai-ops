import hashlib
import secrets
import time
import re
import os
from datetime import datetime
from typing import Optional
from fastapi import Body
from server.db.models.user_model import UserModel
from server.db.session import SessionLocal
from server.utils import BaseResponse

active_tokens = {}

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

def generate_token() -> str:
    return secrets.token_hex(32)

def validate_username(username: str) -> tuple:
    if len(username) < 3:
        return False, "用户名至少需要3个字符"
    if not re.match(r'^[a-zA-Z0-9]+$', username):
        return False, "用户名只能包含英文字母和数字"
    return True, ""

def validate_password(password: str) -> tuple:
    if len(password) < 5:
        return False, "密码至少需要5个字符"
    if len(password) > 10:
        return False, "密码最多10个字符"
    if not re.match(r'^[a-zA-Z0-9]+$', password):
        return False, "密码只能包含英文字母和数字"
    return True, ""

def init_default_user():
    session = SessionLocal()
    try:
        user = session.query(UserModel).filter(UserModel.username == "admin").first()
        if not user:
            user = UserModel(
                username="admin",
                password_hash=hash_password(os.environ.get("DEFAULT_ADMIN_PASSWORD", "admin")),
                role="admin",
                is_active=True,
                created_at=datetime.now()
            )
            session.add(user)
            session.commit()
            print("[OK] 默认用户 admin 已创建（密码通过 DEFAULT_ADMIN_PASSWORD 环境变量设置）")
        return user
    finally:
        session.close()

def register(username: str = Body(...), password: str = Body(...)):
    valid, msg = validate_username(username)
    if not valid:
        return BaseResponse(code=400, msg=msg)
    
    valid, msg = validate_password(password)
    if not valid:
        return BaseResponse(code=400, msg=msg)
    
    session = SessionLocal()
    try:
        existing = session.query(UserModel).filter(UserModel.username == username).first()
        if existing:
            return BaseResponse(code=400, msg="用户名已存在")
        
        user = UserModel(
            username=username,
            password_hash=hash_password(password),
            role="user",
            is_active=True,
            created_at=datetime.now()
        )
        session.add(user)
        session.commit()
        
        return BaseResponse(code=200, msg="注册成功", data={
            "username": user.username,
            "role": user.role
        })
    finally:
        session.close()

def login(username: str = Body(...), password: str = Body(...)):
    session = SessionLocal()
    try:
        user = session.query(UserModel).filter(
            UserModel.username == username,
            UserModel.is_active == True
        ).first()
        
        if not user:
            return BaseResponse(code=401, msg="用户名或密码错误")
        
        if not verify_password(password, user.password_hash):
            return BaseResponse(code=401, msg="用户名或密码错误")
        
        user.last_login = datetime.now()
        session.commit()
        
        token = generate_token()
        active_tokens[token] = {
            "user_id": user.id,
            "username": user.username,
            "role": user.role,
            "login_time": time.time()
        }
        
        return BaseResponse(code=200, msg="登录成功", data={
            "token": token,
            "username": user.username,
            "role": user.role
        })
    finally:
        session.close()

def get_current_user(token: str = None):
    if not token or token not in active_tokens:
        return None
    
    token_data = active_tokens[token]
    session = SessionLocal()
    try:
        user = session.query(UserModel).filter(UserModel.id == token_data["user_id"]).first()
        return user
    finally:
        session.close()

def logout(token: str = Body(..., embed=True)):
    if token in active_tokens:
        del active_tokens[token]
    return BaseResponse(code=200, msg="退出成功")

def verify_token(token: Optional[str] = None):
    if not token or token not in active_tokens:
        return BaseResponse(code=401, msg="未登录或登录已过期")
    
    token_data = active_tokens[token]
    if time.time() - token_data["login_time"] > 86400:
        del active_tokens[token]
        return BaseResponse(code=401, msg="登录已过期，请重新登录")
    
    return BaseResponse(code=200, msg="有效", data=token_data)

def check_auth():
    return BaseResponse(code=200, msg="认证服务正常")
