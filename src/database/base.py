import pymysql
from pymysql.cursors import DictCursor
from typing import Optional, List, Dict, Any
import json

class Database:
    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.connection = None

    def connect(self):
        """建立数据库连接"""
        if not self.connection:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
                charset='utf8mb4',
                collation='utf8mb4_unicode_ci',
                cursorclass=DictCursor
            )

    def disconnect(self):
        """关闭数据库连接"""
        if self.connection:
            self.connection.close()
            self.connection = None

    def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict]:
        """执行查询操作"""
        try:
            self.connect()
            with self.connection.cursor() as cursor:
                cursor.execute(query, params or ())
                return cursor.fetchall()
        finally:
            self.disconnect()

    def execute_update(self, query: str, params: Optional[tuple] = None) -> int:
        """执行更新操作"""
        try:
            self.connect()
            with self.connection.cursor() as cursor:
                affected_rows = cursor.execute(query, params or ())
                self.connection.commit()
                return affected_rows
        finally:
            self.disconnect()

    def execute_insert(self, query: str, params: Optional[tuple] = None) -> int:
        """执行插入操作"""
        try:
            self.connect()
            with self.connection.cursor() as cursor:
                cursor.execute(query, params or ())
                self.connection.commit()
                return cursor.lastrowid
        finally:
            self.disconnect()

    def execute_delete(self, query: str, params: Optional[tuple] = None) -> int:
        """执行删除操作"""
        return self.execute_update(query, params)

    def begin_transaction(self):
        """开始事务"""
        self.connect()
        self.connection.begin()

    def commit_transaction(self):
        """提交事务"""
        if self.connection:
            self.connection.commit()

    def rollback_transaction(self):
        """回滚事务"""
        if self.connection:
            self.connection.rollback() 