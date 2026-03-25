# legacy_v2 Namespace

`legacy_v2/`는 purge 이후에도 이름만 남겨 둔 역사적 namespace다.

현재 상태:

- v2 변환 구현은 workspace에서 제거되었다.
- 이 namespace 아래로 legacy 코드를 다시 옮겨 보관하지 않는다.
- 삭제된 구현은 git history에만 남는다.

남겨 두는 이유:

- 문서상으로 v2와 v3의 경계를 명확히 하기 위해서
- 이후 context compact 상황에서도 "legacy runtime은 더 이상 workspace에 없다"는 사실을 분명히 하기 위해서

원칙:

- 새 기능은 여기에 추가하지 않는다.
- v3가 이 namespace를 import하게 만들지 않는다.
- tombstone stub가 필요하더라도 root public surface에만 제한하고, 여기에 구현을 숨기지 않는다.
