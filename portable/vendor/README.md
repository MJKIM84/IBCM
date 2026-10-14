# 포함 라이브러리

sql.js 1.14.1의 공식 npm 배포본에서 다음 파일을 가져왔습니다.

* `dist/sql-wasm.js`
* `dist/sql-wasm.wasm`
* `LICENSE`

원본 주소는 `https://registry.npmjs.org/sql.js/-/sql.js-1.14.1.tgz`입니다.
다운로드한 압축 파일의 SHA512를 npm 레지스트리가 제공한 다음 integrity 값과 대조했습니다.

```
sha512-gcj8zBWU5cFsi9WUP+4bFNXAyF1iRpA3LLyS/DP5xlrNzGmPIizUeBggKa8DbDwdqaKwUcTEnChtd2grWo/x/A==
```

사용자가 파일을 열 때 라이브러리를 다운로드하지 않습니다. SQLite 실행 코드와 WebAssembly는 HTML에 함께 포함됩니다. 개발자가 다시 파일을 생성할 때도 별도 npm 설치가 필요하지 않습니다.
