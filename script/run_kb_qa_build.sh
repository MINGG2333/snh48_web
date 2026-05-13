cd /home/snh48_web
source venv/bin/activate
python transcript_analyze/run_kb_qa.py \
  --records download_records.json \
  --subtitle-root firered_output_batch \
  --kb-dir video_knowledge_db \
  --debug \
  build
