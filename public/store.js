/* 화면은 이 저장소 통로만 사용하고 실행 환경에 맞는 어댑터가 데이터를 처리합니다. */
(() => {
  "use strict";

  window.IBCM_STORE ||= {
    mode: "server",
    request: (input, options) => window.fetch(input, options)
  };
})();
