import hashlib

from PIL import Image
import pytest

from ml.data.deduplicate import NearConfig, dhash64, duplicate_report


def record(key, content, duration=5.0):
    return {"video_id":key,"sha256":hashlib.sha256(content).hexdigest(),"duration_sec":duration}


def test_exact_cluster_and_near_threshold_are_reproducible_and_separate():
    rows = [record("a",b"a"),record("copy",b"a"),record("reencoded",b"b"),record("other",b"c")]
    samples = {"a":["0000000000000000"]*3, "copy":["0000000000000000"]*3,
               "reencoded":["0000000000000001"]*3, "other":["ffffffffffffffff"]*3}
    result = duplicate_report(rows, samples, config=NearConfig(max_hamming=1))
    assert result == duplicate_report(list(reversed(rows)), samples, config=NearConfig(max_hamming=1))
    assert result["exact_clusters"][0]["video_ids"] == ["a","copy"]
    assert [r["video_ids"] for r in result["near_candidates"]] == [["a","reencoded"],["copy","reencoded"]]
    assert result["near_candidates"][0]["distances"] == [1,1,1]
    strict = duplicate_report(rows, samples, config=NearConfig(max_hamming=0))
    assert strict["near_candidates"] == [] and strict["config_sha256"] != result["config_sha256"]
    assert result["originals_deleted"] is False


def test_short_or_different_duration_is_not_claimed_near_duplicate():
    rows = [record("a",b"a"),record("b",b"b",duration=1)]
    assert not duplicate_report(rows, {"a":["0"*16]*3,"b":["0"*16]*3})["near_candidates"]
    rows[1]["duration_sec"] = 5
    assert not duplicate_report(rows, {"a":["0"*16]*2,"b":["0"*16]*2})["near_candidates"]


def test_actual_dhash_computes_spatial_difference_and_is_bounded():
    image = Image.new("L",(9,8))
    image.putdata([x*20 for y in range(8) for x in range(9)])
    assert dhash64(image) == "0000000000000000"
    image.putdata([(8-x)*20 for y in range(8) for x in range(9)])
    assert dhash64(image) == "ffffffffffffffff"


def test_pair_budget_prevents_unbounded_search():
    with pytest.raises(ValueError,match="budget"):
        duplicate_report([record(str(i),str(i).encode()) for i in range(4)],{},config=NearConfig(max_pairs=1))
