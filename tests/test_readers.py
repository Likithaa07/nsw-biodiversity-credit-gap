"""Tests for the register readers, using tiny files that copy the quirks of the real exports."""
# STEP 1: Imports
import pytest

from common import DataValidationError, MissingInputError
from readers import read_html_register, read_xml_register

# A SpreadsheetML file with a title row, an unescaped '&' and a skipped cell (ss:Index)
XML = """<?xml version="1.0"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
          xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Register"><Table>
  <Row><Cell><Data ss:Type="String">Credit Supply Register</Data></Cell></Row>
  <Row><Cell><Data ss:Type="String">Credit ID</Data></Cell>
       <Cell><Data ss:Type="String">Name</Data></Cell>
       <Cell><Data ss:Type="String">Credits</Data></Cell></Row>
  <Row><Cell><Data ss:Type="String">C1</Data></Cell>
       <Cell><Data ss:Type="String">Box & Gum woodland</Data></Cell>
       <Cell><Data ss:Type="Number">10</Data></Cell></Row>
  <Row><Cell><Data ss:Type="String">C2</Data></Cell>
       <Cell ss:Index="3"><Data ss:Type="Number">5</Data></Cell></Row>
 </Table></Worksheet>
</Workbook>"""

HTML = """<html><body><table>
<tr><th>Transaction ID</th><th>Number of credits</th></tr>
<tr><td>="00018450"</td><td>12</td></tr>
<tr><td>="00018451"</td><td>3</td></tr>
</table></body></html>"""


# STEP 2: XML reader
def test_xml_reader_finds_header_and_restores_skipped_cells(tmp_path):
    path = tmp_path / "Supply.xls"
    path.write_text(XML, encoding="utf-8")
    df = read_xml_register(path, "Credit ID")
    assert list(df.columns) == ["Credit ID", "Name", "Credits"]
    assert len(df) == 2
    assert df.loc[1, "Name"] is None        # the skipped cell is empty...
    assert df.loc[1, "Credits"] == "5"      # ...and the next value lands in the right column


def test_xml_reader_recovers_from_unescaped_ampersand(tmp_path):
    path = tmp_path / "Supply.xls"
    path.write_text(XML, encoding="utf-8")
    assert "Gum woodland" in read_xml_register(path, "Credit ID").loc[0, "Name"]


def test_xml_reader_wrong_header_gives_clear_error(tmp_path):
    path = tmp_path / "Supply.xls"
    path.write_text(XML, encoding="utf-8")
    with pytest.raises(DataValidationError, match="header row"):
        read_xml_register(path, "Not a column")


def test_xml_reader_missing_file(tmp_path):
    with pytest.raises(MissingInputError):
        read_xml_register(tmp_path / "nope.xls", "Credit ID")


# STEP 3: HTML reader
def test_html_reader_strips_formula_wrapper(tmp_path):
    path = tmp_path / "Transactions.xls"
    path.write_text(HTML, encoding="utf-8")
    df = read_html_register(path)
    assert df["Transaction ID"].tolist() == ["00018450", "00018451"]


def test_html_reader_with_no_table(tmp_path):
    path = tmp_path / "Transactions.xls"
    path.write_text("<html><body>nothing here</body></html>", encoding="utf-8")
    with pytest.raises(DataValidationError, match="no HTML table"):
        read_html_register(path)
