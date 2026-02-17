# longcli_run_batch.py 简明用法

批量驱动 `tb run` 跑 long_cli 任务，支持多 agent/model、多任务、多实验设置，串/并行执行或生成脚本。

## 快速开始
```bash
python scripts_python/longcli_run_batch.py \
  --agent-model-pair codex,gpt-5.1-codex-max \
  --task-id 61810_cow 61810_fs \
  --tasks-dir tasks_long_cli \
  --output-path runs_long_cli \
  --exp-setting 1,3 \
  --on-existing skip
```

## 参数速览
- `--agent-model-pair` 可重复：`agent,model` / `agent:model`（默认见脚本内）  
- `--task-id` 列表（默认见脚本内）  
- `--tasks-dir` 传给 `--dataset-path`（默认 `tasks_long_cli`）  
- `--output-path` 结果根目录（默认 `runs_long_cli`）  
- `--exp-setting` 可多组，格式 `n_attempts,test_turn`（默认见脚本内）  
- `--on-existing`：`skip`（默认）或 `overwrite`  
- `--env` 可重复，附加/覆盖环境变量，形如 `KEY=VALUE`  
- `--parallel-dimension`：并行维度，取值 `agent_model_pairs` / `task_ids` / `exp_settings`，可多选  
- `--max-workers`：并行 worker 数  
- `--mode`：`run`（执行）或 `script`（仅生成脚本）  
- `--script-path`：`mode=script` 时脚本输出路径  

## 并行与笛卡尔积
对所有 `agent_model_pairs × task_ids × exp_settings` 生成 run-id。未列入 `--parallel-dimension` 的维度串行，列入的并行；`--max-workers` 限制线程池大小。

## 生成脚本
```bash
python scripts_python/longcli_run_batch.py \
  --mode script --script-path longcli_run_batches.sh \
  --agent-model-pair codex,gpt-5.1-codex-max \
  --task-id 61810_cow \
  --exp-setting 1,3 \
  --env ANTHROPIC_API_KEY=xxx
```
生成的脚本包含环境前缀与 `tb run` 命令，默认可执行。

## 全量示例（含多组与 env）
```bash
python scripts_python/longcli_run_batch.py \
  --agent-model-pair codex,gpt-5.1-codex-max \
  --agent-model-pair claude,claude-3-5-sonnet-20241022 \
  --task-id 61810_cow 61810_fs \
  --exp-setting 1,3 --exp-setting 3,1 \
  --tasks-dir tasks_long_cli \
  --output-path runs_long_cli \
  --on-existing overwrite \
  --env TB_SAVE_APP_RESULT=1 \
  --env ANTHROPIC_API_KEY=sk-xxx \
  --parallel-dimension agent_model_pairs,task_ids \
  --max-workers 4 \
  --mode run
```
生成 2（agent/model）× 2（任务）× 2（exp_setting）= 8 个 run；agent/任务并行，exp_setting 串行，遇到同名目录覆盖。
