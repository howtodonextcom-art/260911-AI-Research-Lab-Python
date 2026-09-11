import json
import unittest

from vietlott_mega645.client import (
    DrawRecord,
    ValidationError,
    discover_history_key,
    parse_detail_html,
    parse_history_html,
    serialize_jsonl,
)


DETAIL_HTML = """
<h5>Kỳ quay thưởng <b>#01561</b> ngày <b>11/09/2026</b></h5>
<div class="day_so_ket_qua_v2">
  <span class="bong_tron">14</span><span class="bong_tron">18</span>
  <span class="bong_tron">20</span><span class="bong_tron">21</span>
  <span class="bong_tron">26</span><span class="bong_tron no-margin-right">27</span>
</div>
"""


HISTORY_HTML = """
<script>
AjaxOut = Vietlott.PlugIn.WebParts.Game645CompareWebPart.ServerSideDrawResult(RenderInfo, '0d11c1d1', GameDrawId, ArrNumbers, CheckMulti, CurrentPageIndex).value;
</script>
<table>
  <tr>
    <td>11/09/2026</td>
    <td><a href="/vi/trung-thuong/ket-qua-trung-thuong/645?id=01561&nocatche=1" target="_self">01561</a></td>
    <td><div class="day_so_ket_qua_v2"><span class="bong_tron ">14</span><span class="bong_tron ">18</span><span class="bong_tron ">20</span><span class="bong_tron ">21</span><span class="bong_tron ">26</span><span class="bong_tron no-margin-right ">27</span></div></td>
  </tr>
  <tr>
    <td>09/09/2026</td>
    <td><a href="/vi/trung-thuong/ket-qua-trung-thuong/645?id=01560&nocatche=1" target="_self">01560</a></td>
    <td><div class="day_so_ket_qua_v2"><span class="bong_tron ">12</span><span class="bong_tron ">17</span><span class="bong_tron ">20</span><span class="bong_tron ">21</span><span class="bong_tron ">36</span><span class="bong_tron no-margin-right ">43</span></div></td>
  </tr>
</table>
"""


class ParserTests(unittest.TestCase):
    def test_parse_detail_html(self):
        row = parse_detail_html(DETAIL_HTML, source_url="https://vietlott.vn/example")
        self.assertEqual(row.id, "01561")
        self.assertEqual(row.date, "2026-09-11")
        self.assertEqual(row.result, (14, 18, 20, 21, 26, 27))
        self.assertEqual(row.source_url, "https://vietlott.vn/example")

    def test_parse_history_html(self):
        rows = parse_history_html(HISTORY_HTML, source_url="https://vietlott.vn/base")
        self.assertEqual([row.id for row in rows], ["01561", "01560"])
        self.assertEqual(rows[1].date, "2026-09-09")
        self.assertEqual(rows[1].result, (12, 17, 20, 21, 36, 43))

    def test_discover_history_key(self):
        self.assertEqual(discover_history_key(HISTORY_HTML), "0d11c1d1")

    def test_record_validation_rejects_bad_result(self):
        with self.assertRaises(ValidationError):
            DrawRecord(date="2026-09-11", id="01561", result=(1, 2, 3, 4, 5, 46))

    def test_serialize_jsonl_is_canonical(self):
        rows = parse_history_html(HISTORY_HTML)
        payload = serialize_jsonl(rows)
        lines = [json.loads(line) for line in payload.splitlines()]
        self.assertEqual([line["id"] for line in lines], ["01560", "01561"])
        self.assertNotIn("source_url", lines[0])


if __name__ == "__main__":
    unittest.main()
