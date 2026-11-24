# 스트리밍 알고리즘 비교 실험

MovieLens 1M의 평점 1,000,209건을 한 줄씩 읽어 Bloom Filter와 Count-Min Sketch를 직접 구현하고 비교합니다. 정확한 사용자·영화 쌍 집합과 영화별 빈도 사전은 평가용 Ground Truth로만 사용합니다.

## 실행 방법

1. Python 3.13 환경에서 필요한 패키지를 설치합니다.

```powershell
python -m pip install -r requirements.txt
```

2. [MovieLens 1M 원본 ZIP](https://files.grouplens.org/datasets/movielens/ml-1m.zip)을 내려받아 압축을 풉니다. 저장소 루트에서 `data/ml-1m/ratings.dat`가 보이도록 놓습니다. 원본 데이터는 GitHub에 포함하지 않았습니다.

3. 실험을 실행합니다.

```powershell
python streaming_experiment.py --ratings data/ml-1m/ratings.dat --output .
```

`results.json`, `bloom_results.csv`, `cms_results.csv`가 갱신됩니다. 저장소의 결과 파일은 난수 시드 `20261124`로 실행한 기록입니다. 처리시간은 컴퓨터와 실행 상태에 따라 달라집니다.

4. 그래프와 PDF 보고서를 재생성하려면 다음을 실행합니다.

```powershell
python make_report.py
```

보고서는 `outputs/streaming_algorithms_report.pdf`, 그래프는 `charts/`에 생성됩니다. 과제 제출물은 PDF 한 파일이며 소스코드는 이 저장소 주소로 확인할 수 있습니다.

## 한글 폰트

PDF에는 한글 TTF 폰트가 필요합니다. Windows에서는 기본적으로 `C:\Windows\Fonts\malgun.ttf`와 `malgunbd.ttf`를 사용합니다. 다른 운영체제이거나 해당 파일이 없으면 설치된 한글 TTF 파일 두 개의 경로를 환경변수로 지정한 뒤 보고서를 생성하세요.

```powershell
$env:REPORT_KOREAN_FONT_REGULAR = "C:\path\to\KoreanRegular.ttf"
$env:REPORT_KOREAN_FONT_BOLD = "C:\path\to\KoreanBold.ttf"
python make_report.py
```

macOS/Linux에서는 각각 `export REPORT_KOREAN_FONT_REGULAR=/path/to/regular.ttf`, `export REPORT_KOREAN_FONT_BOLD=/path/to/bold.ttf`로 지정할 수 있습니다. `.ttc` 대신 `.ttf` 파일을 사용하세요.

## 측정 항목

- Bloom Filter: FPR, false negative 수, 이론 FPR, 자료구조 크기, 구축 시간, 초당 처리량
- Count-Min Sketch: 평균 절대·상대오차, 중앙값 상대오차, 최대 오차, 정확히 일치한 비율, 자료구조 크기, 구축 시간, 초당 처리량
- 파라미터 비교: Bloom 4·8·12·16 bit/item(해시 수 연동), CMS width 512·1024·2048·4096(depth 5 고정)

실험의 핵심 알고리즘은 Python 표준 라이브러리로 구현했습니다. 추가 패키지는 그래프와 PDF 생성에 사용합니다.
