from __future__ import annotations

import json
import math
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

sys.path.insert(0, str(Path(__file__).parent / "vendor"))
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "work" / "results" / "results.json"
CHART_DIR = ROOT / "work" / "charts"
OUTPUT_DIR = ROOT / "outputs"
PDF_PATH = OUTPUT_DIR / "streaming_algorithms_report.pdf"
ZIP_PATH = OUTPUT_DIR / "streaming_assignment_source.zip"

NAVY = colors.HexColor("#15283B")
BLUE = colors.HexColor("#176B87")
TEAL = colors.HexColor("#20A39E")
MINT = colors.HexColor("#DDF3F0")
ORANGE = colors.HexColor("#F29E4C")
PALE = colors.HexColor("#F3F7FA")
GRAY = colors.HexColor("#5E6A73")
LIGHT_GRAY = colors.HexColor("#D9E2E8")
WHITE = colors.white


def mb(value: float) -> str:
    return f"{value / (1024 * 1024):,.2f} MB"


def kb(value: float) -> str:
    return f"{value / 1024:,.1f} KB"


def pct(value: float, digits: int = 2) -> str:
    return f"{value * 100:.{digits}f}%"


def kr_date(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")


def setup_fonts() -> None:
    regular = Path(r"C:\Windows\Fonts\malgun.ttf")
    bold = Path(r"C:\Windows\Fonts\malgunbd.ttf")
    pdfmetrics.registerFont(TTFont("Malgun", str(regular)))
    pdfmetrics.registerFont(TTFont("MalgunBold", str(bold)))
    pdfmetrics.registerFontFamily("Malgun", normal="Malgun", bold="MalgunBold")
    font_manager.fontManager.addfont(str(regular))
    font_manager.fontManager.addfont(str(bold))
    plt.rcParams.update(
        {
            "font.family": "Malgun Gothic",
            "axes.unicode_minus": False,
            "font.size": 9,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.labelcolor": "#31424f",
            "text.color": "#243746",
            "axes.edgecolor": "#b8c6cf",
            "grid.color": "#dce5ea",
        }
    )


def create_charts(data: dict) -> dict[str, Path]:
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    bloom = data["bloom"]
    cms = data["count_min_sketch"]
    paths: dict[str, Path] = {}

    fig, ax1 = plt.subplots(figsize=(7.2, 3.8))
    x = [row["structure_bytes"] / 1024 / 1024 for row in bloom]
    measured = [row["false_positive_rate"] * 100 for row in bloom]
    theoretical = [row["theoretical_fpr"] * 100 for row in bloom]
    ax1.plot(x, measured, marker="o", linewidth=2.4, color="#176B87", label="측정 FPR")
    ax1.plot(x, theoretical, marker="s", linestyle="--", color="#F29E4C", label="이론 FPR")
    ax1.set_yscale("log")
    ax1.set_xlabel("Bloom Filter 크기 (MB)")
    ax1.set_ylabel("False Positive Rate (%) - 로그 축")
    ax1.set_title("Bloom Filter: 메모리 증가에 따른 오탐률 감소")
    ax1.grid(True, which="both", alpha=0.85)
    ax1.legend(frameon=False)
    for xi, yi in zip(x, measured):
        ax1.annotate(f"{yi:.3f}%", (xi, yi), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8)
    fig.tight_layout()
    path = CHART_DIR / "bloom_accuracy.png"
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    paths["bloom_accuracy"] = path

    fig, ax1 = plt.subplots(figsize=(7.2, 3.8))
    labels = [f"{row['bits_per_item']} bit\n(k={row['hash_count']})" for row in bloom]
    throughput = [row["build_throughput"] / 1000 for row in bloom]
    ax1.bar(labels, throughput, color=["#78B7C5", "#4F9BAF", "#2E7D96", "#176B87"], width=0.62)
    ax1.set_ylabel("구축 처리량 (천 건/초)")
    ax1.set_title("Bloom Filter: 해시 수 증가에 따른 처리량 변화")
    ax1.grid(axis="y")
    for i, value in enumerate(throughput):
        ax1.text(i, value + 6, f"{value:.1f}", ha="center", fontsize=8)
    ax1.set_ylim(0, max(throughput) * 1.18)
    fig.tight_layout()
    path = CHART_DIR / "bloom_speed.png"
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    paths["bloom_speed"] = path

    fig, ax1 = plt.subplots(figsize=(7.2, 3.8))
    widths = [row["width"] for row in cms]
    mae = [row["mean_absolute_error"] for row in cms]
    exact = [row["exact_match_rate"] * 100 for row in cms]
    ax1.plot(widths, mae, marker="o", linewidth=2.4, color="#176B87", label="평균 절대오차")
    ax1.set_xlabel("width (depth=5)")
    ax1.set_ylabel("평균 절대오차 (건)", color="#176B87")
    ax1.tick_params(axis="y", labelcolor="#176B87")
    ax1.set_yscale("log")
    ax1.grid(True, which="both")
    ax2 = ax1.twinx()
    ax2.plot(widths, exact, marker="s", linewidth=2.2, color="#F29E4C", label="정확 일치율")
    ax2.set_ylabel("정확 일치율 (%)", color="#C76D16")
    ax2.tick_params(axis="y", labelcolor="#C76D16")
    ax2.set_ylim(0, 105)
    ax1.set_title("Count-Min Sketch: width 증가에 따른 정확도 개선")
    lines = ax1.get_lines() + ax2.get_lines()
    ax1.legend(lines, [line.get_label() for line in lines], frameon=False, loc="center right")
    fig.tight_layout()
    path = CHART_DIR / "cms_accuracy.png"
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    paths["cms_accuracy"] = path

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    labels = ["정확 set\n(멤버십)", "Bloom\n12 bit/item", "정확 dict\n(빈도)", "CMS\n4096x5"]
    values = [
        data["ground_truth"]["pair_set_bytes"] / 1024,
        bloom[2]["structure_bytes"] / 1024,
        data["ground_truth"]["movie_count_dict_bytes"] / 1024,
        cms[3]["structure_bytes"] / 1024,
    ]
    bars = ax.bar(labels, values, color=["#8293A0", "#176B87", "#AAB6BE", "#20A39E"], width=0.62)
    ax.set_yscale("log")
    ax.set_ylabel("자료구조 크기 (KB) - 로그 축")
    ax.set_title("실용 설정과 정확 자료구조의 메모리 비교")
    ax.grid(axis="y", which="both")
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value * 1.18, f"{value:,.0f} KB", ha="center", fontsize=8)
    fig.tight_layout()
    path = CHART_DIR / "memory_comparison.png"
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    paths["memory_comparison"] = path
    return paths


class NumberedCanvas(Canvas):
    def __init__(self, *args, **kwargs):
        Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(page_count)
            Canvas.showPage(self)
        Canvas.save(self)

    def draw_page_number(self, page_count: int):
        if self._pageNumber == 1:
            return
        self.setStrokeColor(LIGHT_GRAY)
        self.setLineWidth(0.5)
        self.line(18 * mm, A4[1] - 13 * mm, A4[0] - 18 * mm, A4[1] - 13 * mm)
        self.setFont("Malgun", 8)
        self.setFillColor(GRAY)
        self.drawString(18 * mm, A4[1] - 10 * mm, "[과제 4] 스트리밍 알고리즘 비교 실험")
        self.setFont("Malgun", 8)
        self.setFillColor(GRAY)
        self.drawRightString(A4[0] - 18 * mm, 11 * mm, f"{self._pageNumber} / {page_count}")


class ReportDoc(BaseDocTemplate):
    def __init__(self, filename: str, **kwargs):
        super().__init__(filename, pagesize=A4, **kwargs)
        frame = Frame(18 * mm, 17 * mm, A4[0] - 36 * mm, A4[1] - 40 * mm, id="normal")
        self.addPageTemplates(PageTemplate(id="main", frames=frame, onPageEnd=self._header))

    def _header(self, canvas: Canvas, doc):
        if doc.page == 1:
            return
        canvas.saveState()
        canvas.setStrokeColor(LIGHT_GRAY)
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, A4[1] - 13 * mm, A4[0] - 18 * mm, A4[1] - 13 * mm)
        canvas.setFont("Malgun", 8)
        canvas.setFillColor(GRAY)
        canvas.drawString(18 * mm, A4[1] - 10 * mm, "[과제 4] 스트리밍 알고리즘 비교 실험")
        canvas.drawRightString(A4[0] - 18 * mm, 11 * mm, str(doc.page))
        canvas.restoreState()


def styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontName="MalgunBold", fontSize=25, leading=34, textColor=WHITE, alignment=TA_LEFT, spaceAfter=8),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"], fontName="Malgun", fontSize=12, leading=19, textColor=colors.HexColor("#DCECF2")),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="MalgunBold", fontSize=18, leading=24, textColor=NAVY, spaceBefore=3, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="MalgunBold", fontSize=12.5, leading=18, textColor=BLUE, spaceBefore=7, spaceAfter=5),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName="Malgun", fontSize=9.2, leading=15.2, textColor=colors.HexColor("#243746"), spaceAfter=6),
        "small": ParagraphStyle("small", parent=base["BodyText"], fontName="Malgun", fontSize=7.6, leading=11.5, textColor=GRAY),
        "callout": ParagraphStyle("callout", parent=base["BodyText"], fontName="MalgunBold", fontSize=10, leading=16, textColor=NAVY, leftIndent=5, rightIndent=5),
        "question": ParagraphStyle("question", parent=base["BodyText"], fontName="MalgunBold", fontSize=10.5, leading=17, textColor=colors.HexColor("#0F596F"), spaceAfter=3),
        "answer": ParagraphStyle("answer", parent=base["BodyText"], fontName="Malgun", fontSize=9.2, leading=15, textColor=colors.HexColor("#243746"), leftIndent=8, spaceAfter=8),
        "table": ParagraphStyle("table", parent=base["BodyText"], fontName="Malgun", fontSize=7.7, leading=10.8, textColor=colors.HexColor("#243746")),
        "table_head": ParagraphStyle("table_head", parent=base["BodyText"], fontName="MalgunBold", fontSize=7.7, leading=10.8, textColor=WHITE, alignment=TA_CENTER),
        "center": ParagraphStyle("center", parent=base["BodyText"], fontName="Malgun", fontSize=8.5, leading=13, alignment=TA_CENTER, textColor=GRAY),
    }


def P(text: str, style) -> Paragraph:
    return Paragraph(text, style)


def section_title(number: str, title: str, s: dict) -> list:
    return [P(f"{number}. {title}", s["h1"]), Table([[""]], colWidths=[28 * mm], rowHeights=[1.4 * mm], style=TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL), ("BOX", (0, 0), (-1, -1), 0, TEAL)])), Spacer(1, 4 * mm)]


def styled_table(rows, widths, s, header=True, align_right_cols=None):
    converted = []
    for ridx, row in enumerate(rows):
        converted.append([
            P(str(cell), s["table_head"] if ridx == 0 and header else s["table"]) for cell in row
        ])
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY if header else PALE),
        ("GRID", (0, 0), (-1, -1), 0.45, LIGHT_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for ridx in range(1 if header else 0, len(rows)):
        if ridx % 2 == 0:
            commands.append(("BACKGROUND", (0, ridx), (-1, ridx), PALE))
    if align_right_cols:
        for col in align_right_cols:
            commands.append(("ALIGN", (col, 1 if header else 0), (col, -1), "RIGHT"))
    return Table(converted, colWidths=widths, repeatRows=1 if header else 0, style=TableStyle(commands))


def callout(text: str, s: dict, color=MINT):
    return Table([[P(text, s["callout"])]], colWidths=[169 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("BOX", (0, 0), (-1, -1), 0.7, TEAL),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))


def metric_cards(metrics: list[tuple[str, str]], s: dict):
    cells = []
    for label, value in metrics:
        cells.append(P(f"<font size='8' color='#5E6A73'>{label}</font><br/><font name='MalgunBold' size='15' color='#15283B'>{value}</font>", s["center"]))
    return Table([cells], colWidths=[42.25 * mm] * len(cells), style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.6, LIGHT_GRAY),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, LIGHT_GRAY),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))


def build_pdf(data: dict, charts: dict[str, Path]) -> None:
    s = styles()
    doc = ReportDoc(str(PDF_PATH), leftMargin=18 * mm, rightMargin=18 * mm, topMargin=17 * mm, bottomMargin=17 * mm, title="스트리밍 알고리즘 2종 구현 및 정확도·메모리 트레이드오프 분석", author="과제 제출자")
    story = []
    bloom = data["bloom"]
    cms = data["count_min_sketch"]
    ds = data["dataset"]
    env = data["environment"]
    gt = data["ground_truth"]

    # Cover
    cover = Table([[P("[과제 4] 스트리밍 알고리즘 비교 실험", s["subtitle"])], [P("스트리밍 알고리즘 2종 구현 및<br/>정확도·메모리 트레이드오프 분석", s["title"])], [P("MovieLens 1M · Bloom Filter · Count-Min Sketch", s["subtitle"])]], colWidths=[169 * mm], rowHeights=[18 * mm, 58 * mm, 18 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 12 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12 * mm),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, colors.HexColor("#365268")),
    ]))
    story += [Spacer(1, 8 * mm), cover, Spacer(1, 12 * mm)]
    story.append(metric_cards([
        ("스트림 레코드", f"{ds['rating_count']:,}"),
        ("Bloom 최저 FPR", pct(bloom[-1]["false_positive_rate"], 3)),
        ("CMS 최저 MAE", f"{cms[-1]['mean_absolute_error']:.2f}"),
        ("최대 처리량", f"{max(x['build_throughput'] for x in bloom + cms)/1000:.1f}K/s"),
    ], s))
    story += [Spacer(1, 11 * mm), P("요약", s["h2"]), P(
        "1,000,209개의 평점 이벤트를 파일에서 한 줄씩 읽어 사용자-영화 쌍의 포함 여부를 Bloom Filter로, 영화별 이벤트 빈도를 Count-Min Sketch로 추정하였다. 두 알고리즘 모두 핵심 자료구조와 해시 로직을 직접 구현했으며, 정확한 set·dictionary 결과와 비교해 정확도, 구조체 메모리, 구축 시간과 처리량을 측정했다.", s["body"]),
        Spacer(1, 3 * mm),
        callout("핵심 결론: 메모리를 늘리면 정확도는 크게 개선됐지만, Bloom Filter는 해시 횟수 증가 때문에 처리량이 감소했다. 실서비스에서는 단일 승자보다 목적에 맞춰 Bloom Filter(빠른 비회원 배제)와 Count-Min Sketch(인기 항목 집계)를 함께 쓰는 구성이 가장 실용적이다.", s),
        Spacer(1, 12 * mm),
        P("작성일  2026-11-24  |  재현 난수 시드  20261124", s["center"]),
        P("소스 배포: 함께 제공된 streaming_assignment_source.zip은 보고서 수치 생성에 사용한 코드와 CSV/JSON 결과를 포함한다. 제출 시 이 압축 파일을 본인 GitHub 공개 저장소에 업로드하고 저장소 URL을 LMS 제출 설명에 기재한다.", s["small"]),
        PageBreak(),
    ]

    # 1 Dataset
    story += section_title("1", "데이터셋 설명", s)
    story += [P("MovieLens 1M은 GroupLens가 제공하는 안정된 벤치마크 데이터로, 사용자 평점 이벤트를 <font name='MalgunBold'>UserID::MovieID::Rating::Timestamp</font> 형식으로 제공한다. 본 실험은 ratings.dat를 한 줄씩 순회했으며 파일 전체를 한 번에 리스트로 로드하지 않았다.", s["body"])]
    rows = [
        ["항목", "실측 값", "활용"],
        ["평점 이벤트", f"{ds['rating_count']:,}건", "스트림의 전체 길이"],
        ["사용자", f"{ds['max_user_id']:,}명", "Bloom 키의 UserID"],
        ["영화", f"{ds['unique_movies']:,}개", "CMS 빈도 추정 대상"],
        ["고유 사용자-영화 쌍", f"{ds['unique_pairs']:,}개", "Bloom 삽입 원소"],
        ["수집 기간", f"{kr_date(ds['min_timestamp'])} ~ {kr_date(ds['max_timestamp'])}", "Timestamp 기준 UTC"],
        ["원본", "GroupLens MovieLens 1M", "https://grouplens.org/datasets/movielens/1m/"],
    ]
    story += [Spacer(1, 2 * mm), styled_table(rows, [42 * mm, 53 * mm, 74 * mm], s), Spacer(1, 7 * mm)]
    story += [P("Ground Truth", s["h2"]), P("Bloom Filter는 모든 사용자-영화 키를 Python set에 저장해 실제 포함 여부를 판정했다. Count-Min Sketch는 영화 ID별 정확한 빈도를 dictionary로 집계했다. 근사 자료구조의 메모리 비교에는 내부 배열의 실제 바이트 수를, 정확 자료구조에는 컨테이너와 정수 객체의 Python 객체 크기를 합산한 값을 사용했다.", s["body"])]
    story.append(styled_table([
        ["정확 자료구조", "크기", "구축 시간", "역할"],
        ["사용자-영화 pair set", mb(gt["pair_set_bytes"]), f"{gt['build_seconds']:.3f}초 (동시 구축)", "멤버십 정답"],
        ["영화 빈도 dictionary", kb(gt["movie_count_dict_bytes"]), f"{gt['build_seconds']:.3f}초 (동시 구축)", "빈도 정답"],
    ], [45 * mm, 32 * mm, 45 * mm, 47 * mm], s))
    story += [Spacer(1, 7 * mm), P("주의: Ground Truth는 평가를 위해 별도로 보유했다. 실제 온라인 운용 시 근사 알고리즘은 이 set·dictionary를 필요로 하지 않는다.", s["small"]), PageBreak()]

    # 2 Algorithms
    story += section_title("2", "선택한 알고리즘 개요", s)
    story += [P("2.1 Bloom Filter", s["h2"]), P("m개의 비트 배열과 k개의 해시 위치를 사용해 집합 포함 여부를 판정한다. 삽입 시 k개 비트를 1로 만들고, 조회 시 하나라도 0이면 확실한 비회원이다. 모두 1이면 회원일 수 있으므로 false positive가 가능하지만, 정상 구현에서는 false negative가 없다. 이론 오탐률은 p ≈ (1 - e<super>-kn/m</super>)<super>k</super>로 계산했다.", s["body"]),
        P("2.2 Count-Min Sketch", s["h2"]), P("depth개의 행과 width개의 카운터 배열을 두고, 항목별로 각 행의 해시 위치를 1씩 증가시킨다. 조회값은 해당 위치들의 최솟값이다. 충돌 때문에 빈도를 과대 추정할 수 있으나 음수가 없는 업데이트 스트림에서는 과소 추정하지 않는다. 메모리는 O(width × depth)로 입력 길이와 무관하게 고정된다.", s["body"]), Spacer(1, 4 * mm)]
    story.append(styled_table([
        ["비교", "Bloom Filter", "Count-Min Sketch"],
        ["질문", "이 사용자-영화 쌍이 이미 있었는가?", "이 영화의 평점 이벤트는 몇 건인가?"],
        ["반환", "아니오(확실) / 예(근사)", "0 이상의 빈도 추정치"],
        ["오차 성격", "false positive 가능", "충돌에 의한 과대 추정"],
        ["핵심 파라미터", "비트 수 m, 해시 수 k", "width w, depth d"],
        ["대표 활용", "중복 요청 사전 필터, 캐시 존재 확인", "인기 키·빈도·heavy hitter 감시"],
    ], [30 * mm, 69.5 * mm, 69.5 * mm], s))
    story += [Spacer(1, 8 * mm), callout("두 알고리즘은 같은 1,000,209건 스트림을 사용하지만 해결하는 질문이 다르다. 따라서 FPR과 빈도 오차를 직접 우열 점수로 합치지 않고, 목적별 정확도와 자원 효율을 비교했다.", s), PageBreak()]

    # 3 Implementation
    story += section_title("3", "구현 방식", s)
    story += [P("모든 핵심 로직은 Python으로 직접 구현했다. 외부 확률 자료구조 라이브러리는 사용하지 않았고, 표와 그래프·PDF 생성에만 matplotlib와 reportlab을 사용했다.", s["body"])]
    impl_rows = [
        ["구성", "구현 상세"],
        ["스트림 입력", "with open(...) 후 각 줄에서 UserID, MovieID, Rating, Timestamp를 즉시 파싱"],
        ["키 인코딩", "pair_key = (UserID << 32) | MovieID로 충돌 없는 64비트 정수 구성"],
        ["해시", "결정론적 64비트 SplitMix64 혼합 함수 사용. Bloom은 double hashing으로 k개 위치 생성"],
        ["Bloom 저장소", "bytearray에 비트를 압축해 저장. structure_bytes = ceil(m/8)"],
        ["CMS 저장소", "행별 array('I') 32비트 unsigned counter. structure_bytes = w × d × 4"],
        ["재현성", "음성 멤버십 쿼리와 양성 표본의 난수 시드를 20261124로 고정"],
    ]
    story += [styled_table(impl_rows, [37 * mm, 132 * mm], s), Spacer(1, 7 * mm)]
    story += [P("평가 절차", s["h2"]), P("(1) 한 번의 순회로 정확 pair set과 movie frequency dictionary를 구축했다. (2) 실제로 존재하지 않는 사용자-영화 쌍 100,000개를 고정 시드로 생성했다. (3) 각 파라미터 설정마다 원본 파일을 다시 한 줄씩 읽어 근사 구조를 새로 구축했다. (4) Bloom은 100,000개 음성 쿼리와 50,000개 양성 표본을, CMS는 3,706개 전체 영화 ID를 조회했다.", s["body"])]
    story += [P("측정의 공정성", s["h2"]), P("시간은 time.perf_counter()로 단일 실행을 측정했다. 디스크 캐시와 Python 인터프리터 영향이 있으므로 절대 시간은 장비 종속적이며, 같은 환경 내 상대 비교에 초점을 둔다. 입력 파싱 비용이 모든 설정에 포함돼 실제 end-to-end 스트림 처리에 가깝다.", s["body"]), PageBreak()]

    # 4 Environment + params
    story += section_title("4", "실험 환경 및 파라미터", s)
    story.append(styled_table([
        ["구분", "환경"],
        ["운영체제", env["platform"]],
        ["프로세서", env["processor"]],
        ["Python", env["python"]],
        ["실험일", "2026-11-24 (Asia/Seoul)"],
        ["입력 방식", "ratings.dat 순차 텍스트 스트리밍"],
    ], [42 * mm, 127 * mm], s))
    story += [Spacer(1, 8 * mm), P("Bloom Filter 파라미터", s["h2"])]
    story.append(styled_table([
        ["bits/item", "해시 수 k", "비트 배열", "구조체 크기"],
        *[[str(r["bits_per_item"]), str(r["hash_count"]), f"{r['bit_count']:,} bit", mb(r["structure_bytes"])] for r in bloom],
    ], [33 * mm, 33 * mm, 56 * mm, 47 * mm], s, align_right_cols=[0, 1, 2, 3]))
    story += [Spacer(1, 7 * mm), P("Count-Min Sketch 파라미터", s["h2"])]
    story.append(styled_table([
        ["width", "depth", "카운터 수", "구조체 크기"],
        *[[f"{r['width']:,}", str(r["depth"]), f"{r['width'] * r['depth']:,}", kb(r["structure_bytes"])] for r in cms],
    ], [33 * mm, 33 * mm, 56 * mm, 47 * mm], s, align_right_cols=[0, 1, 2, 3]))
    story += [Spacer(1, 7 * mm), callout("추가점수용 파라미터 실험: Bloom은 원소당 비트 수와 최적 근사 해시 수를 함께 증가시켰고, CMS는 depth=5를 고정한 채 width를 2배씩 늘렸다.", s), PageBreak()]

    # 5 Bloom results
    story += section_title("5", "Bloom Filter 정확도·메모리·시간 결과", s)
    story.append(styled_table([
        ["bit/item (k)", "크기", "측정 FPR", "이론 FPR", "FN", "구축 시간", "처리량"],
        *[[f"{r['bits_per_item']} ({r['hash_count']})", mb(r["structure_bytes"]), pct(r["false_positive_rate"], 3), pct(r["theoretical_fpr"], 3), str(r["false_negatives"]), f"{r['build_seconds']:.3f}s", f"{r['build_throughput']/1000:.1f}K/s"] for r in bloom],
    ], [24 * mm, 25 * mm, 25 * mm, 25 * mm, 14 * mm, 27 * mm, 29 * mm], s, align_right_cols=[1, 2, 3, 4, 5, 6]))
    story += [Spacer(1, 5 * mm), Image(str(charts["bloom_accuracy"]), width=169 * mm, height=89 * mm), P("그림 1. 실선은 100,000개 비회원 쿼리에서 측정한 FPR, 점선은 이론식의 기대값이다. 두 값이 가깝게 나타나 해시 분포와 구현이 기대 동작을 보였다.", s["small"]), Spacer(1, 4 * mm)]
    story += [callout(f"12 bit/item 설정은 {mb(bloom[2]['structure_bytes'])}만 사용하면서 FPR {pct(bloom[2]['false_positive_rate'], 3)}를 달성했다. exact set {mb(gt['pair_set_bytes'])} 대비 약 {gt['pair_set_bytes']/bloom[2]['structure_bytes']:.1f}배 작아 실용적인 균형점으로 판단한다.", s), PageBreak()]

    story += section_title("6", "Bloom Filter 처리시간 분석", s)
    story += [Image(str(charts["bloom_speed"]), width=169 * mm, height=89 * mm), P("그림 2. 입력 파싱을 포함한 end-to-end 구축 처리량. bit/item이 늘면서 최적 해시 수 k도 3→11로 증가하여 CPU 작업량이 커졌다.", s["small"]), Spacer(1, 6 * mm)]
    story += [P("관찰", s["h2"]), P(f"4 bit/item에서 {bloom[0]['build_throughput']/1000:.1f}천 건/초였던 처리량은 16 bit/item에서 {bloom[-1]['build_throughput']/1000:.1f}천 건/초로 {100*(1-bloom[-1]['build_throughput']/bloom[0]['build_throughput']):.1f}% 감소했다. 반면 FPR은 {pct(bloom[0]['false_positive_rate'],2)}에서 {pct(bloom[-1]['false_positive_rate'],3)}로 약 {bloom[0]['false_positive_rate']/bloom[-1]['false_positive_rate']:.0f}배 개선됐다. 메모리 확대가 정확도를 높였지만 해시 계산 비용까지 증가시켜 시간 성능은 악화된 사례다.", s["body"]),
        P("오차 특성", s["h2"]), P("모든 설정에서 50,000개 실제 회원 표본의 false negative는 0건이었다. 이 속성은 Bloom Filter를 '없음' 판정의 신뢰도가 중요한 캐시 미스·중복 검사 전처리에 적합하게 만든다. 단, 삭제를 지원하지 않으며 비트가 지나치게 차면 FPR이 증가한다.", s["body"]),
        P("권장 설정", s["h2"]), P("일반적인 로그 중복 사전 필터에는 12 bit/item, k=8을 권장한다. 1.43MB로 FPR 0.296%를 달성해 1,000건의 비회원 조회당 약 3건만 후속 정확 조회가 필요하다. 비용이 큰 후속 저장소를 호출하는 환경이라면 16 bit/item도 합리적이다.", s["body"]), PageBreak()]

    # CMS
    story += section_title("7", "Count-Min Sketch 정확도·메모리·시간 결과", s)
    story.append(styled_table([
        ["width×depth", "크기", "MAE", "평균 상대오차", "중앙 상대오차", "정확 일치", "처리량"],
        *[[f"{r['width']}×{r['depth']}", kb(r["structure_bytes"]), f"{r['mean_absolute_error']:.2f}", pct(r["mean_relative_error"],1), pct(r["median_relative_error"],1), pct(r["exact_match_rate"],1), f"{r['build_throughput']/1000:.1f}K/s"] for r in cms],
    ], [27 * mm, 22 * mm, 21 * mm, 27 * mm, 27 * mm, 22 * mm, 23 * mm], s, align_right_cols=[1, 2, 3, 4, 5, 6]))
    story += [Spacer(1, 5 * mm), Image(str(charts["cms_accuracy"]), width=169 * mm, height=89 * mm), P("그림 3. width가 512→4096으로 8배 증가하면서 MAE는 723.40→3.91건으로 감소하고, 정확 일치율은 0.46%→92.17%로 증가했다.", s["small"]), Spacer(1, 4 * mm)]
    story += [callout("평균 상대오차가 MAE보다 크게 보이는 이유는 빈도가 1~수 건인 희소 영화에서 작은 절대 충돌도 큰 비율 오차가 되기 때문이다. 따라서 서비스 의사결정에서는 MAE, 중앙값 상대오차, heavy hitter 순위 보존을 함께 봐야 한다.", s), PageBreak()]

    # Integrated comparison
    story += section_title("8", "통합 메모리·처리시간 비교", s)
    story += [Image(str(charts["memory_comparison"]), width=169 * mm, height=89 * mm), P("그림 4. 자료구조 크기는 로그 축이다. Bloom 12 bit/item은 exact pair set보다 약 43.7배 작고, CMS 4096×5는 exact frequency dictionary보다 약 4.3배 작다.", s["small"]), Spacer(1, 5 * mm)]
    story.append(styled_table([
        ["대표 설정", "정확도", "메모리", "구축 시간", "처리량", "메모리 절감"],
        ["Bloom 12 bit/item", f"FPR {pct(bloom[2]['false_positive_rate'],3)} / FN 0", mb(bloom[2]["structure_bytes"]), f"{bloom[2]['build_seconds']:.3f}s", f"{bloom[2]['build_throughput']/1000:.1f}K/s", f"set 대비 {100*(1-bloom[2]['structure_bytes']/gt['pair_set_bytes']):.1f}%"],
        ["CMS 4096×5", f"MAE {cms[3]['mean_absolute_error']:.2f} / 정확 {pct(cms[3]['exact_match_rate'],1)}", kb(cms[3]["structure_bytes"]), f"{cms[3]['build_seconds']:.3f}s", f"{cms[3]['build_throughput']/1000:.1f}K/s", f"dict 대비 {100*(1-cms[3]['structure_bytes']/gt['movie_count_dict_bytes']):.1f}%"],
    ], [31 * mm, 41 * mm, 25 * mm, 23 * mm, 25 * mm, 24 * mm], s))
    story += [Spacer(1, 7 * mm), P("처리시간 해석", s["h2"]), P("CMS는 5회 해시를 고정했기 때문에 width 증가가 처리량에 뚜렷한 단조 감소를 만들지 않았다(약 25.8만~28.9만 건/초). 배열 크기와 캐시 효과, 단일 실행 잡음이 섞인 결과다. 반대로 Bloom은 k 자체가 증가해 처리량 감소가 명확했다. 즉 파라미터의 의미가 시간 비용에 어떤 경로로 연결되는지를 함께 해석해야 한다.", s["body"]), PageBreak()]

    # Final questions
    story += section_title("9", "알고리즘별 장단점과 최종 분석 질문", s)
    story += [P("Q1. 정확도와 메모리 사이에는 어떤 trade-off가 있었는가?", s["question"]), P("<b>메모리를 늘릴수록 충돌이 줄어 정확도는 크게 좋아졌다.</b> Bloom은 0.48MB에서 1.91MB로 4배 커질 때 FPR이 14.63%에서 0.046%로 약 318배 낮아졌다. CMS는 10KB에서 80KB로 8배 커질 때 MAE가 723.40에서 3.91로 약 185배 낮아졌다. 개선 폭은 컸지만 메모리는 선형으로 늘며, 목표 오차를 넘은 뒤에는 추가 비용 대비 편익을 따져야 한다.", s["answer"]),
        P("Q2. 파라미터 증가가 항상 성능 향상으로 이어졌는가?", s["question"]), P("<b>아니다.</b> 정확도는 개선됐지만 Bloom은 해시 수가 3에서 11로 늘어 처리량이 43.2만에서 22.5만 건/초로 감소했다. CMS에서도 width 증가가 처리시간을 일관되게 줄이지 않았으며 최대 오차는 여전히 존재했다. '성능'을 정확도 하나가 아니라 메모리·지연·처리량까지 포함해 정의해야 한다.", s["answer"]),
        P("Q3. 어떤 알고리즘이 가장 실용적이라고 판단되는가?", s["question"]), P("<b>일반적인 이벤트 빈도 모니터링에는 CMS 4096×5가 가장 실용적이다.</b> 80KB만으로 영화별 빈도의 92.17%를 정확히 맞췄고 MAE가 3.91건이었다. 다만 멤버십 판정이 목적이면 비교 대상이 달라지므로 Bloom 12 bit/item이 더 적합하다. 결국 실용성은 질문과 허용 오류에 의해 결정된다.", s["answer"]),
        P("Q4. 실제 서비스 로그 분석에 적용한다면 어떤 알고리즘을 선택할 것인가?", s["question"]), P("<b>두 알고리즘을 계층적으로 함께 선택한다.</b> 수집 단계에서는 Bloom Filter로 이미 처리한 event_id를 빠르게 걸러 중복 쓰기와 원격 조회를 줄이고, 집계 단계에서는 Count-Min Sketch로 endpoint·검색어·상품 ID 빈도를 고정 메모리로 추적한다. 결제·보안처럼 오탐도 허용하기 어려운 경로에서는 근사 결과 뒤에 정확 저장소 조회를 반드시 둔다.", s["answer"]),
        PageBreak()]

    # Conclusion
    story += section_title("10", "결론", s)
    story += [P("본 실험은 100만 건 이상의 실제 이벤트 스트림에서 두 근사 알고리즘의 장점을 정량적으로 확인했다. Bloom Filter는 exact set 대비 매우 작은 비트 배열로 비회원 여부를 빠르게 판별했고, Count-Min Sketch는 입력 길이와 무관한 작은 카운터 배열로 항목 빈도를 추정했다. 두 알고리즘 모두 메모리 확대가 충돌 감소와 정확도 개선으로 이어졌지만, Bloom에서는 해시 증가가 처리량 하락이라는 직접 비용을 만들었다.", s["body"]),
        callout("최종 권고: 중복/존재 확인에는 Bloom 12 bit/item (k=8), 빈도 모니터링에는 CMS 4096×5를 기본값으로 시작하고, 서비스의 실제 키 분포와 허용 오차·지연 예산에 맞춰 재튜닝한다.", s),
        Spacer(1, 7 * mm), P("한계 및 후속 실험", s["h2"]),
        P("(1) 시간은 한 장비에서 단일 실행했으므로 반복 측정의 신뢰구간을 제시하지 못했다. (2) MovieLens의 영화 ID 분포는 실제 웹 로그의 키 공간과 다르다. (3) CMS의 heavy hitter top-k 정밀도·재현율과 Bloom의 시간 경과에 따른 포화도는 별도 평가가 필요하다. 후속 실험에서는 5회 이상 반복, Zipf 분포 합성 로그, sliding window 또는 decay를 추가하는 것이 바람직하다.", s["body"]),
        Spacer(1, 5 * mm), P("참고문헌 및 데이터", s["h2"]),
        P("[1] GroupLens Research. MovieLens 1M Dataset. https://grouplens.org/datasets/movielens/1m/<br/>[2] Bloom, B. H. (1970). Space/Time Trade-offs in Hash Coding with Allowable Errors. Communications of the ACM, 13(7), 422-426. DOI: 10.1145/362686.362692<br/>[3] Cormode, G. and Muthukrishnan, S. (2005). An Improved Data Stream Summary: The Count-Min Sketch and its Applications. Journal of Algorithms, 55(1), 58-75.", s["small"]),
        Spacer(1, 6 * mm), P("재현 파일", s["h2"]),
        P("streaming_experiment.py: 핵심 알고리즘·실험 실행 / results.json 및 CSV: 원시 결과 / make_report.py: 그래프·보고서 생성 / README.md: 실행 방법. 제출자는 동봉된 source ZIP을 GitHub에 공개한 뒤 해당 저장소 URL을 LMS 제출 설명에 기록한다.", s["body"]),
    ]

    doc.build(story)


def create_source_zip() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    members = [
        ROOT / "work" / "streaming_experiment.py",
        ROOT / "work" / "make_report.py",
        ROOT / "work" / "results" / "results.json",
        ROOT / "work" / "results" / "bloom_results.csv",
        ROOT / "work" / "results" / "cms_results.csv",
        ROOT / "README.md",
        ROOT / "requirements.txt",
    ]
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in members:
            archive.write(path, path.relative_to(ROOT))


def main() -> None:
    setup_fonts()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    charts = create_charts(data)
    build_pdf(data, charts)
    create_source_zip()
    print(PDF_PATH)
    print(ZIP_PATH)


if __name__ == "__main__":
    main()
