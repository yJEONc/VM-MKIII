
let endData = [];
let selectedGrade = null;
let selectedSchool = null;
let currentUnits = [];

async function fetchEndData() {
  const res = await fetch("/api/end_data");
  if (!res.ok) {
    console.error("end 데이터 로드 실패");
    return;
  }
  endData = await res.json();
  buildGradeOptions();
}

function buildGradeOptions() {
  const gradeSelect = document.getElementById("gradeSelect");
  gradeSelect.innerHTML = "";
  const defaultOpt = document.createElement("option");
  defaultOpt.value = "";
  defaultOpt.textContent = "학년을 선택하세요";
  gradeSelect.appendChild(defaultOpt);

  const uniqueGrades = [...new Set(endData.map(d => d.grade))].sort((a,b) => a-b);

  uniqueGrades.forEach(g => {
    const opt = document.createElement("option");
    opt.value = g;
    opt.textContent = `${g}학년`;
    gradeSelect.appendChild(opt);
  });
}

function updateSchoolOptions() {
  const gradeSelect = document.getElementById("gradeSelect");
  const schoolSelect = document.getElementById("schoolSelect");

  const gradeVal = gradeSelect.value;
  selectedGrade = gradeVal ? parseInt(gradeVal, 10) : null;

  // 학교 목록 리셋
  schoolSelect.innerHTML = "";
  const defaultOpt = document.createElement("option");
  defaultOpt.value = "";
  defaultOpt.textContent = "학교를 선택하세요";
  schoolSelect.appendChild(defaultOpt);

  if (!selectedGrade) {
    selectedSchool = null;
    resetMainView();
    return;
  }

  const schools = endData
    .filter(d => d.grade === selectedGrade)
    .map(d => d.school);

  const uniqueSchools = [...new Set(schools)].sort((a, b) => a.localeCompare(b, "ko"));

  uniqueSchools.forEach(s => {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    schoolSelect.appendChild(opt);
  });

  selectedSchool = null;
  resetMainView();
}

async function onSchoolChange() {
  const schoolSelect = document.getElementById("schoolSelect");
  selectedSchool = schoolSelect.value || null;
  if (!selectedGrade || !selectedSchool) {
    resetMainView();
    return;
  }
  await loadPreviewUnits();
}

async function loadPreviewUnits() {
  const body = {
    grade: selectedGrade,
    school: selectedSchool
  };
  const res = await fetch("/api/preview_units", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });

  if (!res.ok) {
    resetMainView();
    return;
  }

  const data = await res.json();
  currentUnits = data.units || [];

  renderMainView(data);
}

function resetMainView() {
  document.getElementById("selectionInfo").style.display = "";
  document.getElementById("contentArea").style.display = "none";
  document.getElementById("btnSeosul").disabled = true;
  document.getElementById("btnChoi").disabled = true;
}

function renderMainView(data) {
  const { grade, school, units } = data;
  document.getElementById("selectionInfo").style.display = "none";
  document.getElementById("contentArea").style.display = "";

  const tagGrade = document.getElementById("tagGrade");
  const tagSchool = document.getElementById("tagSchool");
  tagGrade.textContent = `${grade}학년`;
  tagSchool.textContent = school;

  const matching = endData.find(d => d.grade === grade && d.school === school);
  const tsElem = document.getElementById("latestTimestamp");
  if (matching && matching.timestamp) {
    tsElem.textContent = `최신 업데이트: ${matching.timestamp}`;
  } else {
    tsElem.textContent = "";
  }

  const unitsContainer = document.getElementById("unitsContainer");
  unitsContainer.innerHTML = "";

  let missingCount = 0;

  (units || []).forEach(u => {
    const row = document.createElement("div");
    row.className = "unit-row";

    const colCode = document.createElement("div");
    colCode.className = "unit-code";
    colCode.textContent = u.code;

    const colTitle = document.createElement("div");
    colTitle.className = "unit-title";

    if (!u.has_file) {
      missingCount++;
      const span = document.createElement("span");
      span.className = "unit-missing";
      span.textContent = `${u.title} (서술형/최다빈출 파일 없음)`;
      colTitle.appendChild(span);
    } else {
      colTitle.textContent = u.title ? u.title : "(제목 없음)";
    }

    row.appendChild(colCode);
    row.appendChild(colTitle);
    unitsContainer.appendChild(row);
  });

  const unitsNote = document.getElementById("unitsNote");
  if (missingCount > 0) {
    unitsNote.textContent = `※ (${missingCount})개의 단원은 현재 서술형/최다빈출 파일이 없어 PDF 생성 시 자동으로 제외됩니다.`;
  } else {
    unitsNote.textContent = `모든 단원에 대해 서술형/최다빈출 자료가 준비되어 있습니다.`;
  }

  document.getElementById("btnSeosul").disabled = false;
  document.getElementById("btnChoi").disabled = false;
}

async function mergeMaterial(materialType) {
  if (!selectedGrade || !selectedSchool) return;

  const btnSeosul = document.getElementById("btnSeosul");
  const btnChoi = document.getElementById("btnChoi");
  btnSeosul.disabled = true;
  btnChoi.disabled = true;

  try {
    const res = await fetch(`/merge/${encodeURIComponent(materialType)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        grade: selectedGrade,
        school: selectedSchool
      })
    });

    if (!res.ok) {
      if (res.status === 404) {
        showToast(
          `${selectedSchool} ${selectedGrade}학년 ${materialType}`,
          "해당 자료에 대해 병합할 PDF 파일을 찾을 수 없습니다."
        );
      } else {
        showToast(
          `${selectedSchool} ${selectedGrade}학년 ${materialType}`,
          "PDF 생성 중 오류가 발생했습니다."
        );
      }
      return;
    }

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;

    const today = new Date();
    const y = today.getFullYear();
    const m = String(today.getMonth() + 1).padStart(2, "0");
    const d = String(today.getDate()).padStart(2, "0");
    const filename = `${selectedSchool}_${selectedGrade}학년_${materialType}_${y}${m}${d}.pdf`;

    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);

    showToast(
      `${selectedSchool} ${selectedGrade}학년 ${materialType}`,
      "PDF가 성공적으로 생성되어 다운로드되었습니다."
    );
  } catch (err) {
    console.error(err);
    showToast(
      `${selectedSchool} ${selectedGrade}학년 ${materialType}`,
      "PDF 생성 중 예기치 않은 오류가 발생했습니다."
    );
  } finally {
    btnSeosul.disabled = false;
    btnChoi.disabled = false;
  }
}

async function reloadEndData() {
  try {
    const res = await fetch("/reload", {
      method: "POST"
    });
    if (!res.ok) {
      showToast("시험범위 업데이트", "업데이트 중 오류가 발생했습니다.");
      return;
    }
    const data = await res.json();
    await fetchEndData();
    showToast("시험범위 업데이트", "시험범위 데이터가 최신 버전으로 업데이트되었습니다.");
    if (selectedGrade && selectedSchool) {
      await loadPreviewUnits();
    }
  } catch (err) {
    console.error(err);
    showToast("시험범위 업데이트", "업데이트 중 예기치 않은 오류가 발생했습니다.");
  }
}

let toastTimeout = null;
function showToast(title, message) {
  const toast = document.getElementById("toast");
  const tTitle = document.getElementById("toastTitle");
  const tBody = document.getElementById("toastBody");

  tTitle.textContent = title;
  tBody.textContent = message;

  toast.classList.add("show");

  if (toastTimeout) {
    clearTimeout(toastTimeout);
  }
  toastTimeout = setTimeout(() => {
    toast.classList.remove("show");
  }, 3000);
}

window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("gradeSelect").addEventListener("change", updateSchoolOptions);
  document.getElementById("schoolSelect").addEventListener("change", onSchoolChange);

  document.getElementById("btnSeosul").addEventListener("click", () => mergeMaterial("서술형"));
  document.getElementById("btnChoi").addEventListener("click", () => mergeMaterial("최다빈출"));

  document.getElementById("btnReload").addEventListener("click", reloadEndData);

  fetchEndData();
});
