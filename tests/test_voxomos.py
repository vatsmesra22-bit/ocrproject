"""Voxomos OCR engine: mapping, fallback, DPDP minimisation. The service is faked."""
import httpx
import pytest

from app import config, ocr_table, ocr_voxomos


def fake_client(status=200, body=None, exc=None):
    def handler(request):
        if exc:
            raise exc
        return httpx.Response(status, json=body or {})
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setattr(config, "VOXOMOS_API_KEY", "test-key")
    monkeypatch.setattr(config, "VOXOMOS_URL", "https://ocr.example.com/extract/")


def test_records_mapped_by_title_and_extra_columns_dropped():
    body = {"success": True, "records": [
        {"Account": "11111111111", "Name": "SITA DEVI", "Mobile Nbr": "98765 43210",
         "Village": "X", "Address with Pin": "Y"},
        {"A/C No": "22222222222", "Name1": "RAM", "MobileNo": "", "Father Name": "Z"},
        {"AcNo": "33333333333", "Name": "OP", "MobileNo": "9876500001", "Operative": "OPERATIVE"},
        {"Account": "", "Name": "", "Mobile No": ""}]}
    rows, info = ocr_voxomos.extract(b"img", client=fake_client(body=body))
    assert rows == [
        {"account": "11111111111", "mobile": "9876543210", "name": "SITA DEVI", "low_confidence": False},
        {"account": "22222222222", "mobile": "", "name": "RAM", "low_confidence": False}]
    assert info["skipped_operative"] == 1 and info["engine"] == "voxomos"


@pytest.mark.parametrize("client", [
    fake_client(status=500), fake_client(body={"success": False}),
    fake_client(body={"success": True, "records": []}),
    fake_client(exc=httpx.ConnectError("down"))])
def test_service_problems_raise(client):
    with pytest.raises(ocr_voxomos.VoxomosError):
        ocr_voxomos.extract(b"img", client=client)


def test_falls_back_to_local_ocr(monkeypatch):
    import numpy as np, cv2
    monkeypatch.setattr(config, "OCR_ENGINE", "voxomos")
    monkeypatch.setattr(ocr_voxomos, "extract", lambda data, filename="x": (_ for _ in ()).throw(
        ocr_voxomos.VoxomosError("down")))
    called = []
    monkeypatch.setattr(ocr_table, "run_ocr", lambda img: called.append(1) or [])
    noisy = np.random.default_rng(2).integers(0, 255, (1200, 900, 3), dtype=np.uint8)
    data = cv2.imencode(".jpg", noisy, [cv2.IMWRITE_JPEG_QUALITY, 92])[1].tobytes()
    ocr_table.extract_rows(data, time_limit=0)
    assert called                     # the local engine took over


def test_no_key_means_no_call(monkeypatch):
    monkeypatch.setattr(config, "VOXOMOS_API_KEY", "")
    with pytest.raises(ocr_voxomos.VoxomosError):
        ocr_voxomos.extract(b"img", client=fake_client(exc=AssertionError("must not be called")))


def test_unknown_titles_found_from_values():
    # titles the agent has never seen: columns recognised by their values
    body = {"success": True, "records": [
        {"Col1": "1", "Khata": f"1111111111{i}", "Grahak": f"SITA DEVI {chr(65 + i)}",
         "Sampark": f"987654321{i}"} for i in range(3)]}
    rows, _ = ocr_voxomos.extract(b"img", client=fake_client(body=body))
    assert [(r["account"][-1], r["mobile"][-1], r["name"][-1]) for r in rows] == [
        ("0", "0", "A"), ("1", "1", "B"), ("2", "2", "C")]
