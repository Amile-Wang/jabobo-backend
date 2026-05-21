# 唤醒词训练知识图谱

> 由 GitNexus 从 `jabobo-backend` 代码库索引分析生成（274 符号，605 关系）

---

## 📊 整体架构图

```mermaid
graph TB
    subgraph 前端层["前端 Dashboard"]
        UI[Web 管理界面]
    end

    subgraph API层["jabobo-backend REST API (FastAPI, port 8007)"]
        TrainAPI["POST /api/user/wake-word/train<br>trigger_wake_word_training()"]
        StatusAPI["GET /api/user/wake-word/train/status<br>get_wake_word_status()"]
        SyncAPI["POST /api/user/sync-config<br>sync_config()"]
        GetConfig["GET /api/user/config<br>get_user_config()"]
    end

    subgraph 核心业务层["核心业务流程"]
        direction TB
        NORMALIZE["_normalize_wake_word()<br>标准化唤醒词名"]
        DISPLAY["_wake_word_to_display()<br>生成显示名"]
        TRAIN["_run_wakeword_training()<br>异步训练任务"]
        UPDATE_STATUS["_update_wake_word_status()<br>更新数据库状态"]
    end

    subgraph 外部系统["外部系统"]
        CONDA_ENV["Conda wakeword 环境"]
        TRAIN_SCRIPT["train_wakeword.py<br>（样本生成+模型训练）"]
        DEPLOY_SCRIPT["deploy_wakeword.py<br>（OTA 部署）"]
        TTS_ENGINE["TTS 引擎<br>（多音色）"]
    end

    subgraph 数据层["MySQL 数据库"]
        DB[("user_personas 表")]
    end

    subgraph 固件层["ESP32 设备"]
        DEVICE["捷宝宝硬件"]
        OTA_RECEIVER["OTA 接收+模型加载"]
    end

    %% 前端 → API
    UI -->|POST /user/wake-word/train| TrainAPI
    UI -->|GET /user/wake-word/train/status| StatusAPI
    UI -->|POST /user/sync-config| SyncAPI
    UI -->|GET /user/config| GetConfig

    %% API → 业务
    TrainAPI -->|异步启动| TRAIN
    SyncAPI -->|同步时触发| TRAIN
    GetConfig -.->|读取| DB
    StatusAPI -->|查询| DB

    %% 业务逻辑链
    TRAIN --> NORMALIZE
    NORMALIZE --> DISPLAY
    TRAIN --> UPDATE_STATUS

    %% 训练流程
    TRAIN -->|检查已有模型| TRAIN_SCRIPT
    TRAIN_SCRIPT -->|Step 1: TTS 生成样本| TTS_ENGINE
    TTS_ENGINE -->|"多音色 × 多语速"| TRAIN_SCRIPT
    TRAIN_SCRIPT -->|Step 2: 特征提取+训练| TRAIN_SCRIPT
    TRAIN_SCRIPT -->|输出 .tflite| DEPLOY_SCRIPT
    DEPLOY_SCRIPT -->|OTA 推送| OTA_RECEIVER
    OTA_RECEIVER --> DEVICE

    %% 数据库交互
    UPDATE_STATUS -->|写 model_status| DB
    TRAIN -->|读 trained_models 缓存| TRAIN_SCRIPT
    DEPLOY_SCRIPT -->|写模型文件| TRAIN_SCRIPT

    %% 样式
    classDef api fill:#4A90D9,color:#fff
    classDef biz fill:#2ECC71,color:#fff
    classDef external fill:#F39C12,color:#fff
    classDef db fill:#9B59B6,color:#fff
    classDef device fill:#E74C3C,color:#fff
    classDef front fill:#1ABC9C,color:#fff

    class TrainAPI,StatusAPI,SyncAPI,GetConfig api
    class NORMALIZE,DISPLAY,TRAIN,UPDATE_STATUS biz
    class CONDA_ENV,TRAIN_SCRIPT,DEPLOY_SCRIPT,TTS_ENGINE external
    class DB db
    class DEVICE,OTA_RECEIVER device
    class UI front
```

---

## 🧩 函数调用关系图

```mermaid
graph LR
    subgraph API入口["API 入口"]
        T["trigger_wake_word_training()<br>POST /user/wake-word/train"]
        S["sync_config()<br>POST /user/sync-config<br>（参数含 wake_word_text）"]
        ST["get_wake_word_status()<br>GET /user/wake-word/train/status"]
        GC["get_user_config()<br>GET /user/config<br>（返回 model_status）"]
    end

    subgraph 辅助函数["辅助函数"]
        NW["_normalize_wake_word()<br>🔥 标准化呼唤词名"]
        WD["_wake_word_to_display()<br>生成前端显示名"]
        UV["verify_user()<br>用户认证"]
        GVC["get_valid_cursor()<br>数据库游标"]
        PVL["_parse_voice_list()<br>解析音色列表"]
        VVID["_validate_voice_id()<br>校验音色 ID"]
        VVLI["_validate_voice_list()<br>校验音色列表"]
    end

    subgraph 核心训练["核心训练"]
        RT["_run_wakeword_training()<br>🔥 异步训练任务"]
        US["_update_wake_word_status()<br>🔥 更新模型状态"]
    end

    subgraph 数据库["MySQL"]
        CONN["db.connect()"]
        QUERY["SELECT/UPDATE user_personas"]
    end

    subgraph 外部进程["外部进程"]
        CMD1["train_wakeword.py --generate-samples<br>（TTS 生成 500 条样本）"]
        CMD2["train_wakeword.py<br>（特征提取+训练，输出 .tflite）"]
        CMD3["deploy_wakeword.py<br>（OTA 部署到设备）"]
    end

    %% 调用关系
    T -->|"asyncio.create_task"| RT
    S -.->|"if wake_word_text 有变化"| NW
    NW --> RT
    S -.->|"其他参数同步"| VVID
    S -.->|"其他参数同步"| VVLI
    ST --> UV
    ST --> CONN
    GC --> UV
    GC --> GVC
    GC --> PVL

    RT --> WD
    RT -->|"判断已有模型，跳过训练"| CMD2
    RT -->|"训练"| CMD1
    CMD1 --> CMD2
    CMD2 --> CMD3
    RT --> US
    US --> CONN
    CONN -->|"UPDATE model_status"| QUERY
```

---

## 🕐 完整训练时间线

```mermaid
sequenceDiagram
    participant U as 用户/前端
    participant API as jabobo-backend<br>(FastAPI 8007)
    participant MEM as 进程缓存<br>_wake_word_tasks
    participant DB as MySQL<br>user_personas
    participant CONDA as Conda wakeword 环境
    participant DEV as ESP32 设备

    U->>API: POST /user/wake-word/train<br>{ device_id, wake_word: "Hey Jabra" }
    Note right of API: 标准化: hey_jabra<br>显示名: Hey Jabra
    API->>MEM: 写入 {status: "running"}
    API-->>U: 200 { message: "训练任务已启动" }
    API-->>API: asyncio.create_task<br>_run_wakeword_training()

    rect rgb(240, 248, 255)
        Note over API,CONDA: 阶段1: 生成训练样本
        alt 已有 .tflite 模型
            API-->>API: 跳过训练，直接部署
        else 无模型
            API->>CONDA: train_wakeword.py --generate-samples<br>--text "Hey Jabra" --max-samples 500<br>--voices lessac,amy,joe --length-scales 0.5~1.0
            Note right of CONDA: 多音色 × 5种语速<br>= 数千条 WAV 样本
            CONDA-->>API: 样本生成完成
        end
    end

    rect rgb(255, 248, 240)
        Note over API,CONDA: 阶段2: 模型训练
        API->>CONDA: train_wakeword.py
        Note right of CONDA: MFCC 特征提取<br>CNN 训练<br>TFLite 量化导出
        CONDA-->>API: trained_models/hey_jabra/hey_jabra.tflite
    end

    rect rgb(240, 255, 240)
        Note over API,DEV: 阶段3: OTA 部署
        API->>CONDA: deploy_wakeword.py
        CONDA-->>DEV: OTA 推送 .tflite 模型
        DEV-->>CONDA: 部署确认
    end

    rect rgb(255, 240, 255)
        Note over API,DB: 阶段4: 数据库持久化
        API->>DB: UPDATE user_personas<br>SET wake_word_model_status=1<br>WHERE jabobo_id=xxx
        API->>MEM: 写入 {status: "done", elapsed: 187s}
    end

    U->>API: GET /user/wake-word/train/status?wake_word=hey_jabra&device_id=xxx
    API->>MEM: 读取状态
    API-->>U: { status: "done", elapsed_seconds: 187 }
```

---

## 🗄️ 数据库表关系

```mermaid
erDiagram
    user_login ||--o{ user_personas : has
    user_login {
        int id PK
        string username UK
        string password
        string web_token
        string android_token
        string ios_token
    }
    user_personas {
        int id PK
        string username FK
        string jabobo_id UK
        json personas
        text memory
        string websocket_url
        json websocket_url_list
        string asr_provider
        string tts_provider
        string llm_provider
        json azure_tts_voice_list
        string azure_tts_voice_id
        json huoshan_tts_voice_list
        string huoshan_tts_voice_id
        boolean rag_enabled
        string wake_word_text          "← 用户设定的唤醒词文本"
        int wake_word_model_status     "← 0=未训练, 1=已部署, 2=失败"
        string current_version
        string expected_version
        boolean force_install
        json voiceprint_list
    }
```

---

## 🔧 配置参数

| 参数 | 值 | 说明 |
|------|-----|------|
| `_TRAIN_WORK_DIR` | `~/Jabobo/wakeword train/` | 训练工作目录 |
| `_TRAIN_CONDA_ENV` | `wakeword` | Conda 训练环境 |
| `_TRAIN_LOG_DIR` | `{WORK_DIR}/_training_logs/` | 每轮训练日志 |
| `max-samples` | `500` | 每轮生成样本数 |
| `length-scales` | `0.5 0.6 0.75 0.9 1.0` | 5 种语速 |
| 英文音色 | `lessac, amy, joe, alan, norman, libritts_r` | 6 种 |
| 中文音色 | `chaowen, huayan, xiao_ya` | 3 种 |

---

## 📝 数据库字段说明

```
user_personas.wake_word_text              — 用户自定义唤醒词（如 "Hey Jabra"）
user_personas.wake_word_model_status      — 0=未训练 1=已部署 2=训练失败
```

**状态机：**

```mermaid
stateDiagram-v2
    [*] --> 未训练 : 设备绑定, status=0
    未训练 --> 训练中 : POST /user/wake-word/train
    训练中 --> 已部署 : 训练+部署成功, status=1
    训练中 --> 训练失败 : 异常退出, status=2
    已部署 --> 训练中 : 重新训练
    训练失败 --> 训练中 : 重试
```

---

> 📍 **总结**: 唤醒词训练模块位于 `app/routes/jabobo_config.py`，由以下 15 个函数协同完成：
> - 4 个 API 入口（`trigger_wake_word_training`, `sync_config`, `get_wake_word_status`, `get_user_config`）
> - 3 个核心业务函数（`_run_wakeword_training`, `_normalize_wake_word`, `_wake_word_to_display`）
> - 1 个数据库状态管理（`_update_wake_word_status`）
> - 7 个辅助函数（认证、语音参数校验等）
>
> 外部依赖：Conda `wakeword` 环境、TTS 引擎、`train_wakeword.py`/`deploy_wakeword.py` 脚本
