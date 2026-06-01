# SysOM MCP for AWS

基于 Model Context Protocol (MCP) 的 AWS EC2 系统诊断工具集。在 EC2 实例上本地运行，提供内存、IO、网络、调度、宕机诊断和 EBS 性能分析能力。

## 核心特性

- **20+ 诊断工具** — 覆盖内存、IO、网络、调度、宕机、磁盘、EBS 等
- **容器感知** — Java 内存诊断自动检测 docker/containerd 运行时，exec 进容器执行 jcmd/jmap
- **AWS 集成** — 自动获取 EC2 元数据，通过 CloudWatch 分析 EBS 性能指标（Burst Balance、IOPS、Throughput）
- **Amazon Linux 兼容** — 同时支持 AL2 和 AL2023（cgroup v1/v2、日志系统差异自动适配）
- **双模式运行** — stdio 模式（Qwen Code、Claude Desktop、Cline 等 MCP 客户端）和 SSE 模式（HTTP 服务）

## 快速开始

### 安装

```bash
# 推荐使用 uv
git clone https://github.com/AlexLiu-vibecoding/sysom_mcp_aws.git
cd sysom_mcp_aws
uv sync

# 或者 pip
pip install -e .
```

### 运行

```bash
# stdio 模式（默认，给 AI 客户端用）
python sysom_mcp_aws_server.py --stdio

# SSE 模式（HTTP 服务）
python sysom_mcp_aws_server.py --sse --host 0.0.0.0 --port 7140
```

### Qwen Code 配置

#### 1. 设置环境变量（推荐方式）

Qwen Code 识别 OpenAI 兼容的环境变量，所以用 DeepSeek 的话直接在 `qwen` 前面加：

```bash
OPENAI_API_KEY=sk-your-deepseek-api-key OPENAI_BASE_URL=https://api.deepseek.com/v1 qwen "这台机器的内存是不是有问题？"
```

也可以加到 `~/.bashrc` 里持久化，之后就不用每次输入了：

```bash
echo 'export OPENAI_API_KEY=sk-your-deepseek-api-key' >> ~/.bashrc
echo 'export OPENAI_BASE_URL=https://api.deepseek.com/v1' >> ~/.bashrc
source ~/.bashrc
# 之后直接 qwen 就行
qwen "这台机器的内存是不是有问题？"
```

#### 2. 配置 MCP 服务器

编辑 `~/.qwen/settings.json`：

```json
{
  "mcpServers": {
    "sysom_aws": {
      "command": "uv",
      "args": ["run", "python", "sysom_mcp_aws_server.py", "--stdio"],
      "cwd": "/root/sysom_mcp_aws",
      "timeout": 60000
    }
  }
}
```

> settings.json 不需要填 authType/apiKey/model 这些，Qwen Code 会自动从环境变量读取。

#### 3. 使用

```bash
# 非交互模式（单次问答）
qwen "这台机器的内存是不是有问题？"

# 交互模式（连续对话）
qwen -i
```

Qwen Code 内部流程：
1. 收到问题 → 识别需要诊断数据
2. 通过 MCP 协议调用本地的 `sysom_aws` 服务器（执行 `memgraph` 等命令）
3. 把诊断结果发给 DeepSeek API 解读
4. 返回可读的分析报告

### Claude Desktop 配置（macOS）

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json`：

```json
{
  "mcpServers": {
    "sysom_aws": {
      "command": "uv",
      "args": ["run", "python", "sysom_mcp_aws_server.py", "--stdio"],
      "cwd": "/path/to/sysom_mcp_aws"
    }
  }
}
```

### Claude Desktop 配置（Linux）

```json
{
  "mcpServers": {
    "sysom_aws": {
      "command": "uv",
      "args": ["run", "python", "sysom_mcp_aws_server.py", "--stdio"],
      "cwd": "/path/to/sysom_mcp_aws"
    }
  }
}
```

## 工具清单

### 内存诊断
| 工具 | 说明 |
|------|------|
| `memgraph` | 内存全景分析：free、meminfo、slab、fragmentation、top RSS 进程、NUMA |
| `javamem` | Java 内存诊断：自动发现容器中的 Java 进程，执行 jcmd/jmap/jstat |
| `oomcheck` | OOM 检查：扫描 dmesg/journalctl OOM 事件、watermark、PSI pressure、OOM scores |

### IO 诊断
| 工具 | 说明 |
|------|------|
| `iofsstat` | IO 文件系统统计：mount、df、lsblk、iostat、scheduler、inode、大目录 |
| `iodiagnose` | IO 性能诊断：延迟分析、队列深度、top IO 进程、吞吐量、dmsetup |

### 网络诊断
| 工具 | 说明 |
|------|------|
| `packetdrop` | 网络丢包诊断：接口统计、qdisc、softnet、conntrack、ethtool 驱动计数器 |
| `netjitter` | 网络抖动诊断：RTT 测量、qdisc 延迟、IRQ 分布、TCP buffer、ring buffer 大小 |

### 调度诊断
| 工具 | 说明 |
|------|------|
| `delay` | 调度延迟诊断：schedstat、sched_debug、softirqs、context switch、RCU stall |
| `loadtask` | 负载任务诊断：CPU 热点、线程数、D 状态进程、zombie、run queue |

### 宕机诊断
| 工具 | 说明 |
|------|------|
| `create_vmcore_diagnosis_task` | 创建 VMCORE 诊断任务 |
| `create_dmesg_diagnosis_task` | 创建 dmesg 日志诊断任务（按严重级别分类） |
| `query_diagnosis_task` | 查询诊断任务结果 |
| `list_history_tasks` | 列出历史诊断任务 |

### 其他诊断
| 工具 | 说明 |
|------|------|
| `vmcore` | VMCORE 独立分析 |
| `diskanalysis` | 磁盘分析：用量、块设备、EBS 映射和 CloudWatch 指标 |

### AWS 特定
| 工具 | 说明 |
|------|------|
| `ebs_performance` | EBS 卷性能分析：Burst Balance、IOPS、Throughput、Queue Length（CloudWatch） |
| `ec2_metadata` | EC2 实例元数据：VPC、子网、安全组信息 |

## 项目结构

```
sysom_mcp_aws/
├── README.md
├── pyproject.toml
├── sysom_mcp_aws_server.py      # MCP 服务器主入口
└── src/
    ├── __init__.py
    ├── tools/
    │   ├── __init__.py
    │   ├── memory.py             # memgraph, javamem, oomcheck
    │   ├── io.py                 # iofsstat, iodiagnose
    │   ├── network.py            # packetdrop, netjitter
    │   ├── sched.py              # delay, loadtask
    │   ├── crash.py              # vmcore/dmesg 诊断任务管理
    │   ├── other.py              # vmcore (standalone), diskanalysis
    │   └── aws_ebs.py            # ebs_performance, ec2_metadata
    └── utils/
        ├── __init__.py
        ├── system.py             # 系统命令封装、OS 检测
        ├── container.py          # 容器运行时检测、Java 容器操作
        └── aws.py                # EC2 元数据、EBS CloudWatch 指标查询
```

## 依赖

- Python 3.11+
- boto3（EBS CloudWatch 指标查询）
- MCP Python SDK (>=1.0.0)

## License

Apache License 2.0
