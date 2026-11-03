"""Speaker labels and paragraph breaks survive segmentation."""

from urdu_translator.translation.segments import contains_urdu, segment_document


def test_report_lines_keep_labels_and_blank_lines():
    source = "\n".join(
        [
            "73 SIG CBT SP UNIT",
            "",
            "ROC/ Area:",
            "A-5/ Shahrag",
            "",
            "جمال :۔یہ پہلا جملہ ہے۔",
            "شیخ:۔ یہ دوسرا جملہ ہے۔",
            "نامعلوم:۔ N/H",
            "Analysis: ۔ یہ تجزیہ ہے۔",
        ]
    )
    segments = segment_document(source)
    by_line = {segment.original: segment for segment in segments}

    assert by_line["73 SIG CBT SP UNIT"].needs_translation is False
    assert by_line["ROC/ Area:"].needs_translation is False
    assert by_line["A-5/ Shahrag"].needs_translation is False
    assert by_line["نامعلوم:۔ N/H"].needs_translation is False

    jamal = by_line["جمال :۔یہ پہلا جملہ ہے۔"]
    assert jamal.needs_translation is True
    assert jamal.label == "جمال"
    assert jamal.source_for_engine() == "یہ پہلا جملہ ہے۔"

    sheikh = by_line["شیخ:۔ یہ دوسرا جملہ ہے۔"]
    assert sheikh.label == "شیخ"
    assert sheikh.source_for_engine() == "یہ دوسرا جملہ ہے۔"

    analysis = by_line["Analysis: ۔ یہ تجزیہ ہے۔"]
    assert analysis.label == "Analysis"
    assert analysis.source_for_engine() == "یہ تجزیہ ہے۔"

    assert [segment.original for segment in segments].count("") == 2


def test_plain_urdu_line_is_translated_without_a_label():
    segment = segment_document("یہ سادہ جملہ ہے۔")[0]
    assert segment.label is None
    assert segment.needs_translation is True
    assert segment.source_for_engine() == "یہ سادہ جملہ ہے۔"


def test_crlf_input_is_split_on_lines():
    segments = segment_document("سلام\r\n\r\nدنیا")
    assert [segment.original for segment in segments] == ["سلام", "", "دنیا"]
    assert contains_urdu("سلام") is True
    assert contains_urdu("Freq: 462.225 MHz") is False
