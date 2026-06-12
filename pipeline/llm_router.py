import os, json, requests, time, sys

class LLMRouter:
    def __init__(self):
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.models = [
            "qwen/qwen3-coder:free",
            "deepseek/deepseek-v4-flash:free",
            "openai/gpt-oss-20b:free",
            "nvidia/nemotron-3-ultra:free",
            "google/gemini-2.0-flash-exp:free",
        ]

    def call(self, system_prompt, user_prompt, model=None, max_retries=3):
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")

        models_to_try = [model] if model else self.models

        for attempt in range(max_retries):
            for m in models_to_try:
                try:
                    resp = requests.post(
                        self.base_url,
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": m,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            "temperature": 0.7,
                            "max_tokens": 4096,
                        },
                        timeout=60,
                    )
                    if resp.status_code == 429:
                        print(f"Rate limited on {m}, sleeping 5s...")
                        sys.stdout.flush()
                        time.sleep(5)
                        continue
                    if resp.status_code != 200:
                        print(f"HTTP {resp.status_code} on {m}, retrying...")
                        sys.stdout.flush()
                        continue
                    data = resp.json()
                    content = data["choices"][0]["message"]["content"]
                    print(f"[LLM] Success with {m}")
                    sys.stdout.flush()
                    return content
                except Exception as e:
                    print(f"[LLM] Error with {m}: {e}")
                    sys.stdout.flush()
                    continue
            print(f"Retry {attempt+1}/{max_retries} failed, sleeping 3s...")
            sys.stdout.flush()
            time.sleep(3)
        raise RuntimeError("All LLM models failed")
