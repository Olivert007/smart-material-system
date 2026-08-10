#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CPU 降级 fast 端点（docs/09 降级验证，Stage2 沙箱 GPU 限制期间使用）。

沙箱限制新进程初始化 CUDA（vllm GPU=304 / CPU=NVML 路径 bug），
本脚本用 torch+transformers 纯 CPU 推理提供 OpenAI 兼容端点：
  GET  /v1/models
  POST /v1/chat/completions
启动：nohup python3 scripts/cpu_fast_serve.py > /tmp/cpu_fast.log 2>&1 &
说明：7B bf16 CPU ~1.5 tok/s，仅用于双常驻端点健康/稳定性验证，
     不替代 docs/09 的 GPU fast 生产定位；环境解限后换 vllm GPU。
"""
from __future__ import annotations

import os
import threading
import time
import torch
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel

MODEL = os.environ.get("FAST_MODEL", "/models/Qwen2.5-7B-Instruct")
MODEL_ID = os.environ.get("FAST_MODEL_ID", "qwen2.5-7b")
PORT = int(os.environ.get("FAST_PORT", "8000"))
MAX_TOKENS = int(os.environ.get("FAST_MAX_TOKENS", "512"))

_tokenizer = None
_model = None
_load_lock = threading.Lock()


class ChatReq(BaseModel):
    model: str = MODEL_ID
    messages: list[dict]
    temperature: float = 0.2
    max_tokens: int = 512
    stream: bool = False


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _tokenizer, _model
    with _load_lock:
        if _model is None:
            t0 = time.time()
            from transformers import AutoModelForCausalLM, AutoTokenizer

            _tokenizer = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
            _model = AutoModelForCausalLM.from_pretrained(
                MODEL, dtype=torch.bfloat16, low_cpu_mem_usage=True
            ).to("cpu").eval()
            print(f"CPU_FAST_LOADED {time.time()-t0:.0f}s pid={os.getpid()}", flush=True)
    yield


app = FastAPI(title="cpu-fast", lifespan=lifespan)


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {"id": MODEL_ID, "object": "model", "owned_by": "local-cpu", "cpu_only": True}
        ],
    }


@app.post("/v1/chat/completions")
def chat(req: ChatReq):
    text = "\n".join(
        (m.get("role", "") + ": " if m.get("role") else "") + str(m.get("content", ""))
        for m in req.messages
        if m.get("content")
    )
    ids = _tokenizer(text, return_tensors="pt")
    kwargs = {"max_new_tokens": min(req.max_tokens or MAX_TOKENS, MAX_TOKENS)}
    if (req.temperature or 0) > 0:
        kwargs.update({"do_sample": True, "temperature": max(req.temperature, 1e-3)})
    else:
        kwargs["do_sample"] = False
    with torch.no_grad():
        out = _model.generate(**ids, **kwargs)
    ans = _tokenizer.decode(out[0][ids.input_ids.shape[1]:], skip_special_tokens=True)
    return {
        "id": "chatcmpl-cpu-fast",
        "object": "chat.completion",
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": ans},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": ids.input_ids.shape[1], "completion_tokens": 0, "total_tokens": 0},
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
