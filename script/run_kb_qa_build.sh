cd /home/snh48_web
source venv/bin/activate
python transcript_analyze/run_kb_qa.py \
  --records transcript_analyze/download_records.json \
  --subtitle-root transcript_analyze/firered_output_batch \
  --kb-dir transcript_analyze/video_knowledge_db \
  --debug \
  build
