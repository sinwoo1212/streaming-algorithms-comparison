# 스트리밍 알고리즘 비교 실험

MovieLens 1M 평점 스트림을 한 줄씩 읽으며 Bloom Filter와 Count-Min Sketch를 직접 구현하고 비교하는 프로젝트입니다.

## 실행

1. MovieLens 1M을 내려받아 `work/data/ml-1m/ratings.dat`에 둡니다.
2. 실험을 실행합니다.

```powershell
python work/streaming_experiment.py --ratings work/data/ml-1m/ratings.dat --output work/results
```

핵심 구현은 Python 표준 라이브러리만 사용합니다. `requirements.txt`의 추가 패키지는 그래프와 PDF 보고서 생성 및 검증에 사용됩니다.

## 측정 항목

- Bloom Filter: False Positive Rate, False Negative 수, 이론 FPR, 자료구조 크기, 구축 시간, 처리량
- Count-Min Sketch: 평균 절대/상대 오차, 중앙값 상대 오차, 최대 오차, 정확히 일치한 비율, 자료구조 크기, 구축 시간, 처리량
- Ground Truth: 사용자-영화 쌍 `set`, 영화별 빈도 `dict`

재현성을 위해 난수 시드는 `20261124`로 고정했습니다.
