# Jabobo MySQL 快捷操作脚本使用说明
该脚本用于快速操作Docker容器中的Jabobo项目MySQL数据库，支持交互模式、预设快捷指令、自定义SQL执行三种方式，简化日常数据库查询/操作流程。

## 一、脚本基础信息
### 1. 配置说明
脚本头部配置区已预设核心参数，可根据实际环境修改：
| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `DB_CONTAINER` | Docker MySQL容器名 | `jabobo_final_mysql` |
| `DB_USER` | 数据库用户名 | `root` |
| `DB_PASS` | 数据库密码 | `123456` |
| `DB_NAME` | 目标数据库名 | `jabobo` |
| `DB_HOST` | 数据库地址（容器内） | `127.0.0.1` |
| `DB_PORT` | 数据库端口 | `3307` |

### 2. 脚本权限
执行前需赋予脚本可执行权限：
```bash
chmod +x 脚本名.sh
```

## 二、核心使用方式
### 1. 交互模式（无参数）
直接执行脚本进入MySQL交互终端，可手动输入SQL：
```bash
./脚本名.sh
# 提示：输入 quit 退出交互模式
```

### 2. 预设快捷指令
脚本内置3个高频快捷指令，直接执行即可：
| 指令 | 用途 | 执行命令 |
|------|------|----------|
| `list` | 查看所有设备绑定情况 | `./脚本名.sh list` |
| `index` | 检查表`user_personas`索引 | `./脚本名.sh index` |
| `users` | 查看所有用户账号及角色 | `./脚本名.sh users` |

### 3. 自定义SQL执行
将需要执行的SQL作为参数传入脚本，格式：
```bash
./脚本名.sh "你的SQL语句;"
```

## 三、常用查询SQL（直接复用）
以下SQL均可通过「自定义SQL执行」方式调用，覆盖设备、用户、数据解析等高频场景。

### 1. 设备相关查询
#### 1.1 查询指定设备ID全量数据
```bash
./脚本名.sh "SELECT * FROM user_personas WHERE jabobo_id = '你的设备ID';"
```
用途：精准获取某设备的所有字段（用户名、设备ID、personas、memory等）。

#### 1.2 查询指定用户绑定的所有设备
```bash
./脚本名.sh "SELECT jabobo_id, memory FROM user_personas WHERE username = '你的用户名';"
```
用途：查看某用户下所有绑定设备及对应记忆数据。

#### 1.3 筛选未初始化的设备（无记忆数据）
```bash
./脚本名.sh "SELECT username, jabobo_id FROM user_personas WHERE memory = '尚无记忆' OR memory = '';"
```
用途：排查刚绑定但未初始化的设备。

#### 1.4 统计系统总设备数（去重）
```bash
./脚本名.sh "SELECT COUNT(DISTINCT jabobo_id) AS 总设备数 FROM user_personas;"
```
用途：快速统计绑定设备总数。

### 2. 用户相关查询
#### 2.1 查询指定用户登录信息
```bash
./脚本名.sh "SELECT * FROM user_login WHERE username = '你的用户名';"
```
用途：查看用户ID、角色、session_token等核心信息。

#### 2.2 查询所有管理员账号
```bash
./脚本名.sh "SELECT id, username FROM user_login WHERE role = 'admin';"
```
用途：定位系统管理员账号。

#### 2.3 按角色统计用户数量
```bash
./脚本名.sh "SELECT role, COUNT(*) AS 用户数 FROM user_login GROUP BY role;"
```
用途：统计管理员/普通用户分布。

### 3. 数据解析查询（JSON字段）
#### 3.1 提取设备人设具体内容
```bash
./脚本名.sh "SELECT jabobo_id, JSON_EXTRACT(personas, '$[0].content') AS 默认人设 FROM user_personas WHERE jabobo_id = '你的设备ID';"
```
用途：解析JSON格式的`personas`字段，提取指定位置的内容。

#### 3.2 筛选含指定关键词的设备
```bash
./脚本名.sh "SELECT jabobo_id, username FROM user_personas WHERE personas LIKE '%关键词%';"
```
用途：查找人设包含特定内容的设备。

### 4. 表结构/健康度查询
#### 4.1 查看表完整结构
```bash
./脚本名.sh "DESC user_personas;"
```
用途：查看字段名、类型、默认值等表结构信息。

#### 4.2 排查重复设备ID
```bash
./脚本名.sh "SELECT jabobo_id, COUNT(*) AS 重复次数 FROM user_personas GROUP BY jabobo_id HAVING COUNT(*) > 1;"
```
用途：清理脏数据，排查重复绑定问题。

## 四、注意事项
1. 密码安全：脚本中密码为明文，生产环境建议改为从环境变量读取（`DB_PASS="${DB_PASSWORD:-123456}"`），执行前先设置：`export DB_PASSWORD="你的密码"`；
2. SQL规范：自定义SQL需用双引号包裹，结尾加`;`，避免特殊字符解析错误；
3. 权限限制：脚本基于`root`用户执行，生产环境建议创建只读账号，修改`DB_USER`配置；
4. 容器状态：执行前确保MySQL容器已运行（`docker ps | grep jabobo_final_mysql`），否则会报错。

## 五、常见问题
### Q1：执行脚本提示「docker exec: container not found」？
A1：检查`DB_CONTAINER`配置是否与实际容器名一致，或容器未启动（执行`docker start jabobo_final_mysql`启动）。

### Q2：自定义SQL执行返回空？
A2：确认SQL语法正确，字段名/设备ID/用户名无拼写错误，或数据本身不存在。