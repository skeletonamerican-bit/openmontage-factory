# AI Model Selection — OpenMontage Factory

Цель: выбрать бесплатные модели, оптимальные для Kaggle T4 (16GB RAM), стиль — кинематографический тёмный драматический тон.

## IMAGE GENERATION — Stable Diffusion XL
- Выбор: **Stable Diffusion XL (SDXL)**
- Причины:
  - Хороший баланс качества и потребления памяти на T4 (можно запустить в оптимизированных сборках).
  - Отличная поддержка фотореализма и кинематографической обработки (последующие fine-tune и conditioning).
  - Широкая экосистема инструментов (diffusers, automatic1111/optimizations) и множество готовых кастом-пайплайнов.
- Примечание: FLUX.1-schnell и FLUX.1-dev обеспечивают скоростные опции, но FLUX может быть менее стабильным и совместимым в текущей среде Kaggle. Juggernaut XL даёт лучшую фотореалистичность, но требует больше памяти и часто не помещается в T4.

## VIDEO GENERATION (B-ROLL) — LTX-Video (Lightricks)
- Выбор: **LTX-Video**
- Причины:
  - Оптимизирован для скорости на T4 и даёт приемлемое качество 3–5 сек атмосферных клипов.
  - Обычно легче развернуть в средах с ограниченной VRAM по сравнению с крупными text-to-video моделями.
- Альтернатива: **AnimateDiff** (лучшее качество для image-to-video плавности) — использовать в сценах, где у нас source image-to-video и можно пожертвовать временем.

## VOICE
- Выбор: **Chatterbox** (по требованию) — интегрируется как TTS движок в ноутбуке.

## MUSIC
- Выбор: **YouTube Audio Library (programmatic workflow)**
- Причины:
  - Большая библиотека качественных треков с фильтрацией по настроению (dark, suspenseful).
  - Программный доступ + лицензии, удобные для ютуб-публикации.
- Альтернативы: Pixabay Music API (легко интегрируется) и Freesound (для эффектов). Для основного музыкального слоя — YouTube Audio Library.

## Заметки по реализации на Kaggle T4
- SDXL + LTX-Video — разумный компромисс: SDXL для 8K-like промптов (рендер и кроп), LTX-Video для 3–5s B-roll.
- Нужны оптимизации: mixed precision (bf16/amp), attention slicing, offloading, и частичное CPU-based generation для больших промптов.
- Для тяжелых сцен использовать AnimateDiff или Juggernaut XL локально/GPU с большей памятью.

## Итоговые рекомендации
- Image model: `Stable Diffusion XL` (стартовая модель)
- Video model: `LTX-Video` (основная для быстрых b-roll)
- TTS: `Chatterbox` (уже утверждено)
- Music source: `YouTube Audio Library` (dark/suspenseful selection)

Документ создан автоматически — при желании могу добавить точные команды установки и ссылки на репозитории/weights.