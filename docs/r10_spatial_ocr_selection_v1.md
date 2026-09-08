# R10-O 선택 v1: 단일 공간 단어와 유일한 획 보존 owner

## 사전 관측과 선언

`spatial-ocr-diagnosis-v1`에서 실제3개 overlap cluster를 관측했다. CP/PP는 두scale에서
하나의 고신뢰 단어, Adj는 고신뢰 단어와 낮은 신뢰도의 선→'1' 인식이 나왔다.
이는 개발 관측이며 일반화 증거가 아니다. 아래 첫 후보를 실행 전에 고정한다.

## 고정 규칙

- 기존진단과 같은 crop/border/두scale. 각scale에서 confidence≥.95 단어가 정확히 하나.
  두 단어 text가 일치하고 원본 axis-aligned envelope IoU≥.8이어야 한다.
  단어높이3~32 source s, width/height .5~20, 각polygon 상단각도≤10도.
- 두polygon의 union envelope 안 원본 픽셀을 관측한다. 원본배경은crop ringmedian의
  RGB기반 정수weighted luminance. 밝고균일한배경만 지원한다. core contrast≥80,
  weak≥12. threshold 비교는 정수식(계수2126/7152/722)으로 수행한다.
- 원본전체 core의 8연결 성분 중 envelope 내부에 전체가 들어있는 성분을 glyph seed로
  삼는다. 총core 최소4pixel. envelope를 가로질러 밖으로 나간 성분은 장축span≥3×word높이,
  TLSp95≤2.5s의 실제긴선인 경우에만 별도stroke로 분류한다. 나머지는 ambiguous.
  seed와 외부stroke가8이웃에서닿으면 기권한다.
- glyph support는 core seed에 Chebyshev1 sourcepixel 이내로 이어진 weak pixel 및
  envelope 내부의 별도 작은 weak 성분이다. 외부stroke 자체의 pixel은 glyph로선택하지
  않는다. 별도core없는weak성분을작다는이유로삭제하지않는다. lowcontrast(<12) 차이를
  의미문자로단정하지않고별도잔여량진단을남긴다.
- confidence<.95인 추가OCR영역은 무조건버리지않는다. 해당영역의 core가 위의 실제긴선
  성분으로모두설명되는 경우에만 무시한다. 그렇지않으면 추가글자가능성으로 기권한다.
- 각 owner는 polygon envelope와면적기준≥.5겹쳐야 동일위치후보가된다.
  seedcore100%, weak glyphsupport≥.98을담는 owner가 유일해야선택한다.
  다른 owner가같은글자외별도비선core를포함하면 partial/shared-owner 모호성으로기권한다.
  bbox/ID/score/기존OCR문자는수정하지않고기존 owner하나만 남긴다.
  여러full후보는 padding이나score로임의순위매기지않고기권한다.

## 반례와 실행

입력 OCR관측은 실제RGB에서생성한다. unit은관측함수를대체한고정polygons로선택기
경계를검증하지만 이를end-to-end OCR성적으로세지않는다. 동일내용다른위치두단어,
부분단어, 점,약한별도획,extra저신뢰단어,실제긴선snippet,tie,순서/ID/score,
전체1px이동(구조동일),실제1px획잘림을포함한다. 실제OCR는 별도합성RGB와실제15장으로검증한다.

gates통과후A-T15장O-only추적재실행/native렌더와별도GT평가를실행한다. 이단계의효과가
보이면C+O를별도run으로생성한다. 새FP/독립node손실은실패로기록하고수정한다.
명백한code/fixture bug는revisionbuild로이력을보존하고수정하며,실패기록만남기고중단하지않는다.

## build2 진단 수정

build1 실제3cluster는OCR용좁은crop의ring을배경으로썼고선이ring을가로질러3개모두
background_unsupported였다. 배경은합성padding이아닌실제원본의3word-height주변ring에서
관측하도록수정한다. 또한원래owner가추가로포함하는word밖core도전체성분을검사해야
선과별도글자를구분할수있으므로component query를word+owner union으로정정한다.
core/weak/coverage/직선성임계값은변경하지않는다. 최초구현은별도커밋보존한다.

반례구현전 보수적추가조건: owner가관측word core의80%미만만소유하면부분단어후보로
기권한다. word밖owner영역의weak성분이glyph/stroke의1px근접지원으로설명되지않으면
weak_orphan_outside_word로기권한다. 단순히OCR가못봤다는이유로별도약한획을버리지않는다.
