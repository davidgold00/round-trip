import csv
import json

from deal_agent.news_input import import_news


def test_news_corpus_no_network_idempotent_and_snippet_scope(runtime, deal_dict, tmp_path):
    cfg, store, trace, factory = runtime
    path = tmp_path / "news.csv"
    row = {"url": deal_dict["source_url"], "title": "Nvidia and OpenAI investment",
           "snippet": deal_dict["evidence_quote"], "date": "2025-09-22",
           "publisher": "Nvidia IR", "source_kind": "ir_rss", "financing_relevant": "True"}
    with path.open("w") as f:
        w=csv.DictWriter(f, fieldnames=list(row));w.writeheader();w.writerow(row)
    pipe = factory([{"relevant": True, "reason": "investment"}, {"edges": [deal_dict]}])
    first=import_news(cfg, store, trace, pipe.resolver, path)
    assert first["docs_imported"] == 1 and first["docs_fetched"] == 0
    assert import_news(cfg, store, trace, pipe.resolver, path)["docs_imported"] == 0
    meta=json.loads(store.rows("SELECT meta FROM documents")[0]["meta"])
    assert meta["company"] == "Nvidia" and meta["evidence_tier"] == "T2"
    assert meta["source_scope"] == "news_title_and_snippet_only"
    assert pipe.run_documents()["candidates_proposed"] == 1
    assert pipe.run_documents()["candidates_proposed"] == 0


def test_news_reuses_cached_full_primary_filing(runtime, tmp_path):
    cfg, store, trace, factory = runtime
    interim=tmp_path / "data/interim";interim.mkdir(parents=True)
    raw=tmp_path / "filing.htm";raw.write_text("<p>Nvidia and OpenAI primary investment text.</p>")
    url="https://www.sec.gov/Archives/filing.htm"
    record={"doc_url":url,"node":"Nvidia","form":"8-K","accession_no":"1-25-1","local_path":"filing.htm"}
    with (interim / "filings_index.csv").open("w") as f:
        w=csv.DictWriter(f,fieldnames=list(record));w.writeheader();w.writerow(record)
    row={"url":url,"title":"8-K","snippet":"summary only","date":"2025-09-22","publisher":"Nvidia EDGAR"}
    path=tmp_path/"news.csv"
    with path.open("w") as f:
        w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerow(row)
    assert import_news(cfg,store,trace,factory().resolver,path)["docs_imported"] == 1
    doc=store.rows("SELECT * FROM documents")[0]
    assert json.loads(doc["meta"])["source_scope"] == "cached_primary_filing"
    assert json.loads(doc["meta"])["evidence_tier"] == "T1"
    from pathlib import Path
    assert "primary investment" in Path(doc["text_path"]).read_text()


def test_existing_fetch_document_is_not_downgraded_to_news_snippet(runtime, tmp_path):
    cfg, store, trace, factory = runtime
    url="https://publisher.test/full"
    meta={"source_url":url,"company":"Nvidia","published_date":"2025-09-22","doc_type":"company_release"}
    store.job(url,"document",meta)
    store.save_document(meta,b"full primary text", "full primary text", tmp_path/"raw")
    row={"url":url,"title":"Nvidia and OpenAI investment","snippet":"shorter summary", "date":"2025-09-22","publisher":"Nvidia IR"}
    path=tmp_path/"news.csv"
    with path.open("w") as f:
        w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerow(row)
    result=import_news(cfg,store,trace,factory().resolver,path)
    assert result["docs_imported"] == 0 and result["news_skipped"] == 1
    assert len(store.rows("SELECT * FROM documents")) == 1
