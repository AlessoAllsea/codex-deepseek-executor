---
name: deepseek
description: 用户选择 DeepSeek 执行助手插件或明确要求调用 DeepSeek 时，将范围明确的本机编码任务交给 DeepSeek Harness 实现和测试，再由 Codex 验收。
---

# DeepSeek 执行助手

Codex 负责规划和独立验收，DeepSeek Harness 负责完整子任务的实现、调试和测试。仅在本轮选择本插件、明确点名 DeepSeek，或继续已授权的 DeepSeek 任务时启动；状态、费用和功能问答不触发付费请求。只选择插件而未说明任务时，简短询问项目和目标。

## 首次配置

本插件自带调用器，脚本位于此技能的 `scripts/`，不依赖任何特定用户目录中的工具。只支持 macOS，当前验证版本为 Harness `0.2.1-rc.2`；先阅读 [运行说明](references/runtime.md)。

先运行 `python3 '<本技能绝对路径>/scripts/run.py' --check`。如未配置，且用户已安装官方 dsh、已在本机 Harness 设置中保存 API Key，运行同目录的 `setup.py` 初始化隔离配置。它不读取或复制密钥值，不调用模型，也不改写桌面配置。缺少运行时或认证时，说明具体缺项；认证须由用户在本机设置处理，不索取聊天中的 Key。

## 委派与验收

1. 检查目标项目的 AGENTS.md、已有修改和测试方法。将完整任务的目标、允许修改的路径、边界情况、禁止操作、验收标准和实际测试命令写入项目允许的临时目录。遵守项目文件放置规则，避免与执行 Agent 同时修改相同文件。
2. 使用参数数组或正确引用路径调用：

   ```sh
   python3 '<本技能绝对路径>/scripts/run.py' \
     --workspace '/absolute/project' \
     --task-file '/absolute/task.txt' \
     --result '/absolute/new-result.json' \
     --timeout 900
   ```

   任务正文通过 stdin 传递，不拼入 shell 命令。结果路径必须是新文件。一次委派完整功能，让 DeepSeek 自行实现、测试并修复，最终报告修改文件、实际测试结果和阻碍。
3. 正常等待并简要沟通进度，不频繁读取原始会话或推理。认证、配额、权限、审批或版本校验失败时停止并报告，不反复重试或更换计费通道。
4. 检查 JSON 的 `completed`、`exit_code`、`turn_reason`、`tool_errors`、`protocol_error` 和报告。shell 的非零退出不一定计入工具错误数。再独立审查文件差异并执行必要验证；正常退出不等于业务验收通过。

保持父 Codex 的权限与审批约束。执行器固定采用 `workspace-write` 与 `approval: ask`，不得借本插件越权。默认 900 秒、单次模型输出最多 8192 token，均不是金额上限。DeepSeek 独立 API 计费，Codex 的规划和审查仍消耗其额度。不默认授权提交、推送、部署、对外发消息、软件安装或更多 Agent。
