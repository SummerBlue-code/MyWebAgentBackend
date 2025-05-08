import logging
from typing import Dict, List
from src.database.base import Database

logger = logging.getLogger(__name__)

def check_database_collation(db: Database) -> Dict[str, List[Dict]]:
    """
    检查数据库的字符集和校对规则
    
    Returns:
        Dict[str, List[Dict]]: 包含数据库、表和连接字符集信息的字典
    """
    try:
        # 检查数据库连接字符集
        connection_charset = db.execute_query("SHOW VARIABLES LIKE 'character_set%%'")
        connection_collation = db.execute_query("SHOW VARIABLES LIKE 'collation%%'")
        
        # 获取所有表的信息
        tables = db.execute_query("SHOW TABLE STATUS")
        
        # 获取所有表的列信息
        columns_info = {}
        for table in tables:
            table_name = table['Name']
            columns = db.execute_query(f"SHOW FULL COLUMNS FROM {table_name}")
            columns_info[table_name] = columns
        
        return {
            "connection": {
                "charset": connection_charset,
                "collation": connection_collation
            },
            "tables": tables,
            "columns": columns_info
        }
    except Exception as e:
        logger.error(f"检查数据库字符集时出错: {str(e)}")
        raise

def print_collation_report(db: Database) -> None:
    """
    打印数据库字符集和校对规则的报告
    """
    try:
        report = check_database_collation(db)
        
        print("\n=== 数据库连接字符集设置 ===")
        for var in report["connection"]["charset"]:
            print(f"{var['Variable_name']}: {var['Value']}")
            
        print("\n=== 数据库连接校对规则设置 ===")
        for var in report["connection"]["collation"]:
            print(f"{var['Variable_name']}: {var['Value']}")
            
        print("\n=== 表字符集信息 ===")
        for table in report["tables"]:
            print(f"\n表名: {table['Name']}")
            print(f"字符集: {table['Collation']}")
            
            print("列信息:")
            for column in report["columns"][table['Name']]:
                print(f"  - {column['Field']}: {column['Collation']}")
                
    except Exception as e:
        logger.error(f"打印字符集报告时出错: {str(e)}")
        raise

if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 从配置中获取数据库连接信息
    from src.config.GPTConfig import GPTConfig
    config = GPTConfig()
    
    # 创建数据库连接
    db = Database(
        host=config.db_host,
        port=config.db_port,
        user=config.db_user,
        password=config.db_password,
        database=config.db_name
    )
    
    # 打印报告
    print_collation_report(db)