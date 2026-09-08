# R20 고정 후보의 종류 판정 진단

2026-09-09. R19 `453e8dd`를보존한다. 사용자후속연구목표는미달이다. 이번단계는이미노출된CogBot의저장예측후보94개를고정한개발진단이며새일반화평가가아니다.

## 질문

R19는후보geometry14/17이나종류포함최종1/17이었다. 6노드는맞는종류후보가없고7노드는맞는종류후보가.95미달이었다. 온전한테두리가보이는ROI도오인했다. **같은bbox에서해상도/주변문맥/내부잉크를바꾸면고정분류기의종류판정이달라지는가?** 학습을더하기전에이구별을한다.

## 네 조건

R19 final.pt와sourceRGB/저장bbox를동결하고bbox회귀·RPN을재실행하지않는다. torchvision의동일FrozenBN backbone/ROIAlign/box_head/box_predictor만평가한다. post-regression bbox를다시ROIAlign하므로원래R19저장score와조건A의score가정확히같을필요는없다. A를네조건의새공통대조로삼는다.

- A full600: 전체RGB min600/max960,고정bboxROIAlign.
- B full1200: 전체RGB min1200/max1920,동일bboxROIAlign. 원본좌표bbox불변.
- C local: 각예측bbox에가로세로15%문맥을추가한원본RGB crop. min600/max960후같은bbox의상대좌표로ROIAlign.
- D local_ablated: C와같지만bbox중앙가로/세로60%를bbox테두리12%띠의RGB중앙값으로대체한다. 목적은내부잉크의존진단이다. 잘못된bbox에서는이조작이실제테두리까지지울수있으므로“텍스트만삭제”로주장하지않는다.

class0포함7종softmax를저장한다. 최고구조종류score≥.95인후보만고정bbox로출력하고네조건모두confidence우선class-agnostic IoU>.7중복제거를동일적용한다. 포함관계만으로부모/자식을제거하지않는다. threshold/중복기준을결과후바꾸지않는다. nativepreset/noFill PPT와실제COM을생성한다.GT로crop하거나bbox를수정하지않는다.

94개bbox를최초저장예측과대조하고image/model/code/spec/bbox SHA를실행전후검사한다. 수동17node장부는네조건의예측파일저장이끝난뒤별도진단에서만읽는다. 기하일치조건에서종류가어떻게달라지는지,최종TP/FP/FN,source/변형ROI/실제COM을육안으로비교한다.

## 판정 한계와 후속

성공여부를이노출원본하나의수치로정하지않는다. C가개선되면문맥/scale shortcut가설, D가추가개선되면내부잉크shortcut가설을지지하는개발증거로만본다. 실제사용승인이나독립일반화는아니다. 다음학습/후처리는이결과를본뒤새사전등록과미개봉평가로진행한다. 남은candidate_absent3개는별도문제다.
