#!/usr/bin/env python3
"""
CLAP 零样本 BGM 识别
=================================================
对抖音视频的音频做背景音乐分类（判断「有无 BGM」+「BGM 类型」）。

用法：
  python3 classify_bgm.py --video v_xxx.mp4 [--video v_yyy.mp4 ...]
  python3 classify_bgm.py --wav sample.wav
  python3 classify_bgm.py --video v_xxx.mp4 --top 3

输出：每条音频的 Top-K 标签 + 置信度（softmax 后）
"""
import argparse
import json
import os
import sys

import numpy as np
import torch
import soundfile as sf


# 候选标签池 —— 覆盖抖音常见 BGM 类型 + 「无 BGM」判断
# 注：标签聚焦「音乐类型 + 有无伴奏」，避免用情绪形容词（容易与类型混淆、分散置信度）
CANDIDATES = [
    "中国传统民乐",
    "流行歌曲",
    "钢琴曲",
    "电子音乐",
    "管弦乐",
    "摇滚乐",
    "鼓点节奏感强的音乐",
    "吉他弹唱",
    "纯人声说话，没有音乐伴奏",
]


def load_audio(path, target_sr=48000):
    """用 soundfile 加载音频，转单声道、重采样到 target_sr，返回 float32 numpy。"""
    data, sr = sf.read(path, dtype="float32")
    if data.ndim > 1:
        data = data.mean(axis=1)  # 单声道
    if sr != target_sr:
        import torchaudio
        wf = torch.from_numpy(data).unsqueeze(0)
        resampler = torchaudio.transforms.Resample(sr, target_sr)
        data = resampler(wf).squeeze(0).numpy()
    return data.astype(np.float32), target_sr


def extract_audio(video_path, out_wav, duration=10.0, sr=48000):
    """从视频提取前 N 秒音频为单声道 wav。"""
    import subprocess
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-i", video_path,
        "-t", str(duration), "-vn", "-ac", "1", "-ar", str(sr), out_wav,
    ]
    subprocess.run(cmd, check=True)
    return out_wav


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", action="append", default=[], help="视频文件路径（可多次）")
    ap.add_argument("--wav", action="append", default=[], help="wav 路径（可多次）")
    ap.add_argument("--model", default="laion/clap-htsat-unfused", help="CLAP 模型名")
    ap.add_argument("--top", type=int, default=3, help="输出 Top-K")
    ap.add_argument("--duration", type=float, default=10.0, help="提取音频秒数")
    ap.add_argument("--tmpdir", default=None, help="临时 wav 目录")
    ap.add_argument("--json", default=None, help="额外输出 JSON 到指定文件")
    args = ap.parse_args()

    # 懒加载模型（首次会在线下载，约 300MB）
    from transformers import ClapModel, ClapProcessor

    print(f"[CLAP] 加载模型 {args.model} ...", file=sys.stderr)
    model = ClapModel.from_pretrained(args.model)
    processor = ClapProcessor.from_pretrained(args.model)
    model.eval()

    # 文本标签 embedding
    text_inputs = processor(text=CANDIDATES, return_tensors="pt", padding=True)
    with torch.no_grad():
        text_emb = model.get_text_features(**text_inputs)
    # transformers 5.x 返回 BaseModelOutputWithPooling，取 pooler_output
    text_emb = getattr(text_emb, "pooler_output", text_emb)
    text_emb = text_emb / text_emb.norm(dim=-1, keepdim=True)

    import tempfile
    tmpdir = args.tmpdir or tempfile.mkdtemp(prefix="bgm_")
    os.makedirs(tmpdir, exist_ok=True)

    # 音频输入：视频 + wav
    audio_paths = []
    for v in args.video:
        wav = os.path.join(tmpdir, os.path.splitext(os.path.basename(v))[0] + ".wav")
        extract_audio(v, wav, duration=args.duration)
        audio_paths.append((os.path.basename(v), wav))
    for w in args.wav:
        audio_paths.append((os.path.basename(w), w))

    print("\n" + "=" * 64)
    json_out = {}
    for name, wav in audio_paths:
        waveform, sr = load_audio(wav)
        # 截取前 duration 秒
        n = int(args.duration * sr)
        if waveform.shape[0] > n:
            waveform = waveform[:n]

        inputs = processor(audio=waveform, return_tensors="pt", sampling_rate=sr)
        with torch.no_grad():
            audio_emb = model.get_audio_features(**inputs)
        audio_emb = getattr(audio_emb, "pooler_output", audio_emb)
        audio_emb = audio_emb / audio_emb.norm(dim=-1, keepdim=True)

        logits = audio_emb @ text_emb.T  # (1, K)
        probs = torch.softmax(logits / 0.07, dim=-1).squeeze(0).numpy()
        order = np.argsort(-probs)

        top_labels = [
            {"label": CANDIDATES[i], "score": round(float(probs[i]), 4)}
            for i in order[: args.top]
        ]
        json_out[name] = {"top": top_labels}

        print(f"📁 {name}")
        for i in order[: args.top]:
            print(f"   {probs[i]*100:5.1f}%  {CANDIDATES[i]}")
        print("-" * 64)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(json_out, f, ensure_ascii=False, indent=2)
        print(f"\nJSON 已写 → {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
