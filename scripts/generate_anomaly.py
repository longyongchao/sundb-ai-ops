#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
D-Bot 异常注入引擎
支持三种异常模式：slow_sql, lock, log
用法：
    python scripts/generate_anomaly.py --type slow_sql --duration 30
    python scripts/generate_anomaly.py --type lock --duration 20
    python scripts/generate_anomaly.py --type log --count 100
"""
import argparse
import os
import sys
import time
import random
import threading
import json
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 数据库配置
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "user": "postgres",
    "password": "123456",
    "database": "dbgpt_metadata"
}

# 日志输出目录
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "anomaly")


class AnomalyInjector:
    """异常注入器基类"""
    
    def __init__(self):
        self.conn = None
        self.cursor = None
        self.running = False
        
    def connect(self):
        """连接数据库"""
        try:
            import psycopg2
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cursor = self.conn.cursor()
            print(f"[OK] 已连接数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
            return True
        except Exception as e:
            print(f"[ERROR] 数据库连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开数据库连接"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        print("[OK] 数据库连接已关闭")
    
    def create_test_table(self, table_name="anomaly_test"):
        """创建测试表"""
        try:
            self.cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            self.cursor.execute(f"""
                CREATE TABLE {table_name} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100),
                    value INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            self.conn.commit()
            print(f"[OK] 测试表 {table_name} 创建成功")
            return True
        except Exception as e:
            print(f"[ERROR] 创建测试表失败: {e}")
            return False
    
    def drop_test_table(self, table_name="anomaly_test"):
        """删除测试表"""
        try:
            self.cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            self.conn.commit()
            print(f"[OK] 测试表 {table_name} 已删除")
        except Exception as e:
            print(f"[WARNING] 删除测试表失败: {e}")


class SlowSQLInjector(AnomalyInjector):
    """慢SQL注入器 - 模拟CPU波动"""
    
    def __init__(self, duration=30):
        super().__init__()
        self.duration = duration
        self.table_name = "slow_sql_test"
    
    def inject(self):
        """注入慢SQL异常"""
        print(f"\n[注入] 慢SQL异常 (持续时间: {self.duration}秒)")
        print("=" * 50)
        
        if not self.connect():
            return {"success": False, "error": "数据库连接失败"}
        
        try:
            # 创建测试表
            if not self.create_test_table(self.table_name):
                return {"success": False, "error": "创建测试表失败"}
            
            # 插入大量数据
            print("[INFO] 正在插入大量测试数据...")
            for i in range(10000):
                self.cursor.execute(
                    f"INSERT INTO {self.table_name} (name, value) VALUES (%s, %s)",
                    (f"name_{random.randint(1, 100000)}", random.randint(1, 1000))
                )
                if i % 1000 == 0:
                    self.conn.commit()
                    print(f"  已插入 {i} 条记录...")
            self.conn.commit()
            print(f"[OK] 已插入 10000 条测试数据")
            
            # 执行无索引的复杂查询（模拟慢SQL）
            print(f"\n[INFO] 开始执行慢查询 (持续 {self.duration} 秒)...")
            start_time = time.time()
            query_count = 0
            
            while time.time() - start_time < self.duration:
                # 复杂的关联查询（无索引）
                self.cursor.execute(f"""
                    SELECT a.name, COUNT(*) as cnt
                    FROM {self.table_name} a
                    JOIN {self.table_name} b ON a.value = b.value
                    WHERE a.name LIKE '%{random.randint(1, 100)}%'
                    GROUP BY a.name
                    ORDER BY cnt DESC
                    LIMIT 10
                """)
                results = self.cursor.fetchall()
                query_count += 1
                
                if query_count % 5 == 0:
                    elapsed = time.time() - start_time
                    print(f"  已执行 {query_count} 次查询, 已用时 {elapsed:.1f}秒")
            
            total_time = time.time() - start_time
            print(f"\n[OK] 慢SQL注入完成!")
            print(f"  - 总查询次数: {query_count}")
            print(f"  - 实际耗时: {total_time:.1f}秒")
            
            return {
                "success": True,
                "type": "slow_sql",
                "duration": total_time,
                "query_count": query_count,
                "records_inserted": 10000
            }
            
        except Exception as e:
            print(f"[ERROR] 慢SQL注入失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            self.drop_test_table(self.table_name)
            self.disconnect()


class LockInjector(AnomalyInjector):
    """锁竞争注入器 - 模拟死锁或行锁"""
    
    def __init__(self, duration=20, threads=5):
        super().__init__()
        self.duration = duration
        self.threads = threads
        self.table_name = "lock_test"
        self.lock_results = []
    
    def inject(self):
        """注入锁竞争异常"""
        print(f"\n[注入] 锁竞争异常 (持续时间: {self.duration}秒, 线程数: {self.threads})")
        print("=" * 50)
        
        if not self.connect():
            return {"success": False, "error": "数据库连接失败"}
        
        try:
            # 创建测试表
            if not self.create_test_table(self.table_name):
                return {"success": False, "error": "创建测试表失败"}
            
            # 插入初始数据
            print("[INFO] 正在插入初始数据...")
            for i in range(100):
                self.cursor.execute(
                    f"INSERT INTO {self.table_name} (name, value) VALUES (%s, %s)",
                    (f"item_{i}", i)
                )
            self.conn.commit()
            print(f"[OK] 已插入 100 条初始数据")
            
            # 启动多线程锁竞争
            print(f"\n[INFO] 启动 {self.threads} 个线程进行锁竞争...")
            start_time = time.time()
            
            threads = []
            for i in range(self.threads):
                t = threading.Thread(target=self._lock_worker, args=(i, start_time))
                t.start()
                threads.append(t)
            
            # 等待所有线程完成
            for t in threads:
                t.join()
            
            total_time = time.time() - start_time
            print(f"\n[OK] 锁竞争注入完成!")
            print(f"  - 实际耗时: {total_time:.1f}秒")
            print(f"  - 总更新次数: {sum(self.lock_results)}")
            
            return {
                "success": True,
                "type": "lock",
                "duration": total_time,
                "threads": self.threads,
                "total_updates": sum(self.lock_results)
            }
            
        except Exception as e:
            print(f"[ERROR] 锁竞争注入失败: {e}")
            return {"success": False, "error": str(e)}
        finally:
            self.drop_test_table(self.table_name)
            self.disconnect()
    
    def _lock_worker(self, thread_id, start_time):
        """锁竞争工作线程"""
        import psycopg2
        update_count = 0
        
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            while time.time() - start_time < self.duration:
                # 随机更新一行（模拟行锁竞争）
                row_id = random.randint(1, 100)
                cursor.execute(
                    f"UPDATE {self.table_name} SET value = value + 1 WHERE id = %s",
                    (row_id,)
                )
                conn.commit()
                update_count += 1
                
                # 随机短暂休眠
                time.sleep(random.uniform(0.01, 0.05))
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            print(f"  [线程{thread_id}] 错误: {e}")
        
        self.lock_results.append(update_count)
        print(f"  [线程{thread_id}] 完成, 更新次数: {update_count}")


class LogInjector:
    """日志注入器 - 生成PostgreSQL格式的错误日志"""
    
    def __init__(self, count=100):
        self.count = count
        self.log_dir = LOG_DIR
    
    def inject(self):
        """注入错误日志"""
        print(f"\n[注入] 错误日志 (数量: {self.count})")
        print("=" * 50)
        
        # 确保日志目录存在
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 日志文件路径
        log_file = os.path.join(self.log_dir, f"postgresql_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        
        # 错误类型模板
        error_templates = [
            "ERROR:  deadlock detected",
            "ERROR:  canceling statement due to statement timeout",
            "ERROR:  duplicate key value violates unique constraint",
            "ERROR:  relation \"{}\" does not exist",
            "ERROR:  column \"{}\" does not exist",
            "ERROR:  permission denied for table {}",
            "ERROR:  out of memory",
            "ERROR:  too many connections",
            "WARNING:  there is no transaction in progress",
            "FATAL:  sorry, too many clients already",
            "ERROR:  could not extend file",
            "ERROR:  disk full",
        ]
        
        try:
            with open(log_file, 'w') as f:
                for i in range(self.count):
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    pid = random.randint(1000, 9999)
                    error = random.choice(error_templates)
                    
                    # 格式化错误消息
                    if '{}' in error:
                        table_name = f"table_{random.randint(1, 100)}"
                        error = error.format(table_name)
                    
                    log_line = f"{timestamp} UTC [{pid}] {error}\n"
                    f.write(log_line)
                    
                    if (i + 1) % 20 == 0:
                        print(f"  已生成 {i + 1} 条日志...")
            
            print(f"\n[OK] 错误日志生成完成!")
            print(f"  - 日志文件: {log_file}")
            print(f"  - 日志数量: {self.count}")
            
            return {
                "success": True,
                "type": "log",
                "log_file": log_file,
                "count": self.count
            }
            
        except Exception as e:
            print(f"[ERROR] 日志生成失败: {e}")
            return {"success": False, "error": str(e)}


def main():
    parser = argparse.ArgumentParser(description='D-Bot 异常注入引擎')
    parser.add_argument('--type', type=str, required=True, 
                        choices=['slow_sql', 'lock', 'log'],
                        help='异常类型: slow_sql(慢SQL), lock(锁竞争), log(错误日志)')
    parser.add_argument('--duration', type=int, default=30,
                        help='异常持续时间(秒), 默认30秒')
    parser.add_argument('--threads', type=int, default=5,
                        help='锁竞争线程数, 默认5')
    parser.add_argument('--count', type=int, default=100,
                        help='日志生成数量, 默认100条')
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("D-Bot 异常注入引擎")
    print("=" * 50)
    print(f"异常类型: {args.type}")
    print(f"参数: duration={args.duration}, threads={args.threads}, count={args.count}")
    
    result = None
    
    if args.type == 'slow_sql':
        injector = SlowSQLInjector(duration=args.duration)
        result = injector.inject()
    elif args.type == 'lock':
        injector = LockInjector(duration=args.duration, threads=args.threads)
        result = injector.inject()
    elif args.type == 'log':
        injector = LogInjector(count=args.count)
        result = injector.inject()
    
    print("\n" + "=" * 50)
    print("注入结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 50)
    
    return result


if __name__ == '__main__':
    main()