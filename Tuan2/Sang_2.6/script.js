document.addEventListener("DOMContentLoaded", () => {
  const demoButton = document.getElementById("demoButton");
  const sendButton = document.getElementById("sendButton");
  const promptCode = document.getElementById("promptCode");
  const promptModel = document.getElementById("promptModel");
  const promptStatus = document.getElementById("promptStatus");
  const zeroShotBlock = document.getElementById("zeroShotBlock");
  const fewShotBlock = document.getElementById("fewShotBlock");

  if (demoButton) {
    demoButton.addEventListener("click", () => {
      alert("Demo chức năng: Đây là trang web tĩnh, bạn có thể mở rộng bằng API OpenAI hoặc Gemini.");
    });
  }

  if (sendButton) {
    sendButton.addEventListener("click", () => {
      const name = document.getElementById("name").value.trim();
      const message = document.getElementById("message").value.trim();
      if (!name || !message) {
        alert("Vui lòng nhập tên và tin nhắn trước khi gửi.");
        return;
      }
      alert(`Cảm ơn ${name}! Tin nhắn của bạn đã được ghi nhận.`);
      document.getElementById("name").value = "";
      document.getElementById("message").value = "";
    });
  }

  const runDemoButton = document.getElementById("runDemoButton");
  const apiStatus = document.getElementById("apiStatus");
  const apiLoading = document.getElementById("apiLoading");
  const zeroShotOutput = document.getElementById("zeroShotOutput");
  const fewShotOutput = document.getElementById("fewShotOutput");
  const apiModel = document.getElementById("apiModel");
  const apiComparison = document.getElementById("apiComparison");

  if (promptCode && promptModel && promptStatus && zeroShotBlock && fewShotBlock) {
    fetch("prompt.py")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Không thể đọc prompt.py (${response.status})`);
        }
        return response.text();
      })
      .then((text) => {
        promptCode.textContent = text;
        promptStatus.textContent = "Đã tải xong";

        const modelMatch = text.match(/MODEL_NAME\s*=\s*os\.environ\.get\(\s*"OPENAI_MODEL"\s*,\s*"([^"]+)"\s*\)/);
        const modelStaticMatch = text.match(/MODEL_NAME\s*=\s*"([^"]+)"/);
        const modelName = modelMatch ? modelMatch[1] : modelStaticMatch ? modelStaticMatch[1] : "Không tìm thấy";
        promptModel.textContent = modelName;

        const zeroShotMatch = text.match(/zero_shot_prompt\s*=\s*f?"""([\s\S]*?)"""/i);
        const fewShotMatch = text.match(/few_shot_prompt\s*=\s*f?"""([\s\S]*?)"""/i);

        zeroShotBlock.textContent = zeroShotMatch ? zeroShotMatch[1].trim() : "Không tìm thấy Zero-shot prompt.";
        fewShotBlock.textContent = fewShotMatch ? fewShotMatch[1].trim() : "Không tìm thấy Few-shot prompt.";
      })
      .catch((error) => {
        promptCode.textContent = error.message;
        promptStatus.textContent = "Lỗi tải file";
      });
  }

  function setLoading(isLoading) {
    if (!apiLoading) return;
    apiLoading.classList.toggle("hidden", !isLoading);
  }

  function setStatus(message) {
    if (!apiStatus) return;
    apiStatus.textContent = message;
  }

  function buildComparisonTable(items) {
    if (!items || !items.length) return "<p>Không có dữ liệu so sánh.</p>";
    const rows = items
      .map(
        (item) => `
          <tr>
            <td>${item.criteria}</td>
            <td>${item.zero_shot}</td>
            <td>${item.few_shot}</td>
          </tr>
        `
      )
      .join("");
    return `
      <table>
        <thead>
          <tr>
            <th>Tiêu chí</th>
            <th>Zero-shot</th>
            <th>Few-shot</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  if (runDemoButton && apiStatus && apiLoading && zeroShotOutput && fewShotOutput && apiModel) {
    runDemoButton.addEventListener("click", async () => {
      setStatus("Đang gọi API backend...");
      setLoading(true);
      zeroShotOutput.textContent = "Đang chờ dữ liệu...";
      fewShotOutput.textContent = "Đang chờ dữ liệu...";
      apiModel.textContent = "-";

      try {
        const response = await fetch("/api/demo");
        const data = await response.json();
        if (!response.ok || !data.success) {
          const message = data.error || data.detail || response.statusText || "Lỗi khi gọi API";
          throw new Error(message);
        }

        const result = data.data;
        apiModel.textContent = result.model || "Không xác định";
        zeroShotOutput.textContent = result.zero_shot_output || "Không có dữ liệu.";
        fewShotOutput.textContent = result.few_shot_output || "Không có dữ liệu.";
        setStatus("API trả về thành công.");

        if (apiComparison) {
          apiComparison.innerHTML = buildComparisonTable(result.comparison);
        }
      } catch (error) {
        setStatus(`Lỗi: ${error.message}`);
        zeroShotOutput.textContent = "Lỗi khi lấy dữ liệu.";
        fewShotOutput.textContent = "Lỗi khi lấy dữ liệu.";
      } finally {
        setLoading(false);
      }
    });
  }
});