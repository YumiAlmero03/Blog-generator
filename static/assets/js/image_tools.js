(function () {
  const ratioInput = document.getElementById("snap_ratio");
  const pixelWidthInput = document.getElementById("pixel_width");
  const pixelHeightInput = document.getElementById("pixel_height");
  const imageFileInput = document.getElementById("image_file");
  const cropScaleSlider = document.getElementById("cropScaleSlider");
  const cropScaleValue = document.getElementById("cropScaleValue");
  const useWatermarkInput = document.getElementById("use_watermark");
  const watermarkControls = document.getElementById("watermarkControls");
  const watermarkPositionInput = document.getElementById("watermark_position");
  const watermarkOpacityInput = document.getElementById("watermark_opacity");
  const logoScaleInput = document.getElementById("logo_scale");
  const watermarkRotationSlider = document.getElementById("watermarkRotationSlider");
  const watermarkRotationValue = document.getElementById("watermarkRotationValue");
  const cropStage = document.getElementById("cropStage");
  const cropImage = document.getElementById("cropImage");
  const cropBox = document.getElementById("cropBox");
  const cropHandle = cropBox ? cropBox.querySelector(".crop-handle") : null;
  const watermarkPreview = document.getElementById("watermarkPreview");
  const cropPlaceholder = document.getElementById("cropPlaceholder");
  const cropMeta = document.getElementById("cropMeta");
  const cropXInput = document.getElementById("crop_x");
  const cropYInput = document.getElementById("crop_y");
  const cropWidthInput = document.getElementById("crop_width");
  const cropHeightInput = document.getElementById("crop_height");
  const cropScaleInput = document.getElementById("crop_scale");
  const watermarkXInput = document.getElementById("watermark_x");
  const watermarkYInput = document.getElementById("watermark_y");
  const watermarkRotationInput = document.getElementById("watermark_rotation");

  if (!ratioInput || !pixelWidthInput || !pixelHeightInput || !cropStage || !cropImage || !cropBox || !cropScaleSlider || !cropScaleInput) {
    return;
  }

  const ratioMap = {
    "1:1": [1, 1],
    "4:5": [4, 5],
    "16:9": [16, 9],
    "9:16": [9, 16],
    "3:2": [3, 2],
  };

  const state = {
    naturalWidth: 0,
    naturalHeight: 0,
    scale: 1,
    boxLeft: 0,
    boxTop: 0,
    boxWidth: 0,
    boxHeight: 0,
    dragging: false,
    resizing: false,
    dragOffsetX: 0,
    dragOffsetY: 0,
    resizeAnchorX: 0,
    resizeAnchorY: 0,
    objectUrl: null,
    activeDimension: "width",
    watermarkLeft: 0,
    watermarkTop: 0,
    watermarkWidth: 0,
    watermarkHeight: 0,
    watermarkDragging: false,
    watermarkOffsetX: 0,
    watermarkOffsetY: 0,
  };

  function setMeta(message) {
    if (cropMeta) {
      cropMeta.textContent = message;
    }
  }

  function getCurrentRatio() {
    if (ratioInput.value === "original") {
      return [state.naturalWidth || 1, state.naturalHeight || 1];
    }
    return ratioMap[ratioInput.value] || [state.naturalWidth || 1, state.naturalHeight || 1];
  }

  function syncOutputDimensions(changedField) {
    const width = parseInt(pixelWidthInput.value || "0", 10);
    const height = parseInt(pixelHeightInput.value || "0", 10);
    const ratio = getCurrentRatio();
    const ratioWidth = ratio[0];
    const ratioHeight = ratio[1];
    state.activeDimension = changedField || state.activeDimension;

    if (state.activeDimension === "height") {
      if (height > 0) {
        pixelWidthInput.value = String(Math.max(1, Math.round(height * (ratioWidth / ratioHeight))));
      }
    } else if (width > 0) {
      pixelHeightInput.value = String(Math.max(1, Math.round(width * (ratioHeight / ratioWidth))));
    }
  }

  function updateHiddenFields() {
    if (!state.scale || state.boxWidth <= 0 || state.boxHeight <= 0) {
      cropXInput.value = "0";
      cropYInput.value = "0";
      cropWidthInput.value = "";
      cropHeightInput.value = "";
      return;
    }

    cropXInput.value = String(Math.round(state.boxLeft / state.scale));
    cropYInput.value = String(Math.round(state.boxTop / state.scale));
    cropWidthInput.value = String(Math.round(state.boxWidth / state.scale));
    cropHeightInput.value = String(Math.round(state.boxHeight / state.scale));
    cropScaleInput.value = cropScaleSlider.value;
    if (watermarkPreview && watermarkXInput && watermarkYInput) {
      const centerX = state.watermarkLeft + (state.watermarkWidth / 2);
      const centerY = state.watermarkTop + (state.watermarkHeight / 2);
      watermarkXInput.value = String(Math.round((centerX / state.boxWidth) * 1000) / 10);
      watermarkYInput.value = String(Math.round((centerY / state.boxHeight) * 1000) / 10);
    }
    if (watermarkRotationInput && watermarkRotationSlider) {
      watermarkRotationInput.value = watermarkRotationSlider.value;
    }
  }

  function clampWatermarkPosition(left, top) {
    if (!watermarkPreview) {
      return;
    }
    const maxLeft = Math.max(0, state.boxWidth - state.watermarkWidth);
    const maxTop = Math.max(0, state.boxHeight - state.watermarkHeight);
    state.watermarkLeft = Math.min(Math.max(0, left), maxLeft);
    state.watermarkTop = Math.min(Math.max(0, top), maxTop);
  }

  function applyWatermarkPreset() {
    if (!watermarkPreview || !watermarkPositionInput || (useWatermarkInput && !useWatermarkInput.checked)) {
      return;
    }
    const presets = {
      "top-left": [15, 15],
      "top-right": [85, 15],
      "bottom-left": [15, 85],
      "center": [50, 50],
      "bottom-right": [85, 85],
    };
    const selected = presets[watermarkPositionInput.value] || presets["bottom-right"];
    watermarkXInput.value = String(selected[0]);
    watermarkYInput.value = String(selected[1]);
    initializeWatermark(false);
  }

  function renderWatermark() {
    if (!watermarkPreview) {
      return;
    }
    if (useWatermarkInput && !useWatermarkInput.checked) {
      watermarkPreview.style.display = "none";
      return;
    }
    watermarkPreview.style.display = "block";
    watermarkPreview.style.width = state.watermarkWidth + "px";
    watermarkPreview.style.left = state.watermarkLeft + (state.watermarkWidth / 2) + "px";
    watermarkPreview.style.top = state.watermarkTop + (state.watermarkHeight / 2) + "px";
    watermarkPreview.style.opacity = String(Math.max(0, Math.min(100, parseInt(watermarkOpacityInput ? watermarkOpacityInput.value || "100" : "100", 10))) / 100);
    const rotation = watermarkRotationSlider ? watermarkRotationSlider.value : "0";
    watermarkPreview.style.transform = "translate(-50%, -50%) rotate(" + rotation + "deg)";
    if (watermarkRotationValue) {
      watermarkRotationValue.textContent = "Rotation: " + rotation + " deg";
    }
  }

  function initializeWatermark(useSavedPosition) {
    if (!watermarkPreview || !state.boxWidth || !state.boxHeight) {
      return;
    }
    if (useWatermarkInput && !useWatermarkInput.checked) {
      watermarkPreview.style.display = "none";
      return;
    }
    const scalePercent = Math.max(1, Math.min(100, parseInt(logoScaleInput ? logoScaleInput.value || "20" : "20", 10)));
    state.watermarkWidth = Math.max(32, state.boxWidth * (scalePercent / 100));
    const previewImage = watermarkPreview.querySelector("img");
    const previewRatio = previewImage && previewImage.naturalWidth && previewImage.naturalHeight
      ? previewImage.naturalHeight / previewImage.naturalWidth
      : 1;
    state.watermarkHeight = Math.max(24, state.watermarkWidth * previewRatio);

    let centerXPercent = 85;
    let centerYPercent = 85;
    if (useSavedPosition && watermarkXInput && watermarkYInput) {
      centerXPercent = parseFloat(watermarkXInput.value || "85");
      centerYPercent = parseFloat(watermarkYInput.value || "85");
    }
    state.watermarkLeft = (state.boxWidth * (centerXPercent / 100)) - (state.watermarkWidth / 2);
    state.watermarkTop = (state.boxHeight * (centerYPercent / 100)) - (state.watermarkHeight / 2);
    clampWatermarkPosition(state.watermarkLeft, state.watermarkTop);
    renderWatermark();
    updateHiddenFields();
  }

  function renderBox() {
    cropBox.style.left = state.boxLeft + "px";
    cropBox.style.top = state.boxTop + "px";
    cropBox.style.width = state.boxWidth + "px";
    cropBox.style.height = state.boxHeight + "px";
    initializeWatermark(true);
    updateHiddenFields();
    if (cropScaleValue) {
      cropScaleValue.textContent = "Crop box size: " + cropScaleSlider.value + "%";
    }
    setMeta("Crop area: " + (cropWidthInput.value || 0) + " x " + (cropHeightInput.value || 0) + "px. Drag to reposition it.");
  }

  function disableCrop(message) {
    cropBox.hidden = true;
    updateHiddenFields();
    if (message) {
      setMeta(message);
    }
  }

  function clampPosition(left, top) {
    const maxLeft = Math.max(0, cropImage.clientWidth - state.boxWidth);
    const maxTop = Math.max(0, cropImage.clientHeight - state.boxHeight);
    state.boxLeft = Math.min(Math.max(0, left), maxLeft);
    state.boxTop = Math.min(Math.max(0, top), maxTop);
  }

  function initializeCropBox() {
    if (!state.naturalWidth || !state.naturalHeight || !cropImage.clientWidth || !cropImage.clientHeight) {
      disableCrop("Load an image to start framing the crop.");
      return;
    }
    state.scale = cropImage.clientWidth / state.naturalWidth;
    const ratio = getCurrentRatio();
    const stageWidth = cropImage.clientWidth;
    const stageHeight = cropImage.clientHeight;
    const sliderScale = Math.max(20, Math.min(100, parseInt(cropScaleSlider.value || cropScaleInput.value || "70", 10)));
    const previousCenterX = state.boxLeft + (state.boxWidth / 2);
    const previousCenterY = state.boxTop + (state.boxHeight / 2);

    let widthByStage = stageWidth * (sliderScale / 100);
    let heightByStage = widthByStage * (ratio[1] / ratio[0]);
    if (heightByStage > stageHeight * (sliderScale / 100)) {
      heightByStage = stageHeight * (sliderScale / 100);
      widthByStage = heightByStage * (ratio[0] / ratio[1]);
    }

    widthByStage = Math.min(widthByStage, stageWidth);
    heightByStage = Math.min(heightByStage, stageHeight);

    state.boxWidth = widthByStage;
    state.boxHeight = heightByStage;
    if (previousCenterX > 0 && previousCenterY > 0) {
      state.boxLeft = previousCenterX - (state.boxWidth / 2);
      state.boxTop = previousCenterY - (state.boxHeight / 2);
    } else {
      state.boxLeft = (stageWidth - state.boxWidth) / 2;
      state.boxTop = (stageHeight - state.boxHeight) / 2;
    }
    clampPosition(state.boxLeft, state.boxTop);
    cropBox.hidden = false;
    syncOutputDimensions(state.activeDimension);
    renderBox();
  }

  function loadPreview(url) {
    cropStage.classList.remove("empty");
    cropImage.hidden = false;
    if (cropPlaceholder) {
      cropPlaceholder.hidden = true;
    }
    cropImage.src = url;
  }

  function handleImageLoad() {
    state.naturalWidth = cropImage.naturalWidth;
    state.naturalHeight = cropImage.naturalHeight;
    initializeCropBox();
  }

  function getPointerPosition(event) {
    const rect = cropStage.getBoundingClientRect();
    return {
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    };
  }

  function stopDragging(event) {
    if (!state.dragging && !state.resizing && !state.watermarkDragging) {
      return;
    }
    state.dragging = false;
    state.resizing = false;
    state.watermarkDragging = false;
    cropBox.classList.remove("dragging");
    if (watermarkPreview) {
      watermarkPreview.classList.remove("dragging");
    }
    if (event && cropBox.hasPointerCapture(event.pointerId)) {
      cropBox.releasePointerCapture(event.pointerId);
    }
    if (event && cropHandle && cropHandle.hasPointerCapture(event.pointerId)) {
      cropHandle.releasePointerCapture(event.pointerId);
    }
    if (event && watermarkPreview && watermarkPreview.hasPointerCapture(event.pointerId)) {
      watermarkPreview.releasePointerCapture(event.pointerId);
    }
  }

  cropImage.addEventListener("load", handleImageLoad);
  if (cropImage.complete && cropImage.naturalWidth) {
    handleImageLoad();
  }

  cropBox.addEventListener("pointerdown", function (event) {
    if (event.target === cropHandle || event.target === watermarkPreview || (watermarkPreview && watermarkPreview.contains(event.target))) {
      return;
    }
    if (cropBox.hidden) {
      return;
    }
    state.dragging = true;
    cropBox.classList.add("dragging");
    const position = getPointerPosition(event);
    state.dragOffsetX = position.x - state.boxLeft;
    state.dragOffsetY = position.y - state.boxTop;
    cropBox.setPointerCapture(event.pointerId);
  });

  cropBox.addEventListener("pointermove", function (event) {
    if (!state.dragging) {
      return;
    }
    const position = getPointerPosition(event);
    clampPosition(position.x - state.dragOffsetX, position.y - state.dragOffsetY);
    renderBox();
  });

  if (cropHandle) {
    cropHandle.addEventListener("pointerdown", function (event) {
      if (cropBox.hidden) {
        return;
      }
      state.resizing = true;
      cropBox.classList.add("dragging");
      state.resizeAnchorX = state.boxLeft;
      state.resizeAnchorY = state.boxTop;
      cropHandle.setPointerCapture(event.pointerId);
      event.stopPropagation();
    });

    cropHandle.addEventListener("pointermove", function (event) {
      if (!state.resizing) {
        return;
      }
      const position = getPointerPosition(event);
      const ratio = getCurrentRatio();
      const maxWidth = cropImage.clientWidth - state.resizeAnchorX;
      const maxHeight = cropImage.clientHeight - state.resizeAnchorY;
      let nextWidth = Math.max(40, position.x - state.resizeAnchorX);
      let nextHeight = nextWidth * (ratio[1] / ratio[0]);
      if (nextHeight > maxHeight) {
        nextHeight = maxHeight;
        nextWidth = nextHeight * (ratio[0] / ratio[1]);
      }
      if (nextWidth > maxWidth) {
        nextWidth = maxWidth;
        nextHeight = nextWidth * (ratio[1] / ratio[0]);
      }
      state.boxWidth = nextWidth;
      state.boxHeight = nextHeight;
      const scaleByWidth = (state.boxWidth / cropImage.clientWidth) * 100;
      const scaleByHeight = (state.boxHeight / cropImage.clientHeight) * 100;
      cropScaleSlider.value = String(Math.max(20, Math.min(100, Math.round(Math.max(scaleByWidth, scaleByHeight)))));
      renderBox();
    });
  }

  if (watermarkPreview) {
    watermarkPreview.addEventListener("pointerdown", function (event) {
      if (cropBox.hidden || (useWatermarkInput && !useWatermarkInput.checked)) {
        return;
      }
      state.watermarkDragging = true;
      watermarkPreview.classList.add("dragging");
      const position = getPointerPosition(event);
      state.watermarkOffsetX = position.x - state.boxLeft - state.watermarkLeft;
      state.watermarkOffsetY = position.y - state.boxTop - state.watermarkTop;
      watermarkPreview.setPointerCapture(event.pointerId);
      event.stopPropagation();
    });

    watermarkPreview.addEventListener("pointermove", function (event) {
      if (!state.watermarkDragging) {
        return;
      }
      const position = getPointerPosition(event);
      clampWatermarkPosition(
        position.x - state.boxLeft - state.watermarkOffsetX,
        position.y - state.boxTop - state.watermarkOffsetY
      );
      renderWatermark();
      updateHiddenFields();
    });
  }

  cropBox.addEventListener("pointerup", stopDragging);
  cropBox.addEventListener("pointercancel", stopDragging);
  if (cropHandle) {
    cropHandle.addEventListener("pointerup", stopDragging);
    cropHandle.addEventListener("pointercancel", stopDragging);
  }
  if (watermarkPreview) {
    watermarkPreview.addEventListener("pointerup", stopDragging);
    watermarkPreview.addEventListener("pointercancel", stopDragging);
  }

  ratioInput.addEventListener("change", function () {
    syncOutputDimensions(state.activeDimension);
    initializeCropBox();
  });

  cropScaleSlider.addEventListener("input", initializeCropBox);

  if (useWatermarkInput) {
    useWatermarkInput.addEventListener("change", function () {
      if (watermarkControls) {
        watermarkControls.classList.toggle("is-hidden", !useWatermarkInput.checked);
      }
      if (watermarkPreview) {
        renderWatermark();
      }
    });
  }

  if (watermarkPositionInput) {
    watermarkPositionInput.addEventListener("change", applyWatermarkPreset);
  }

  if (logoScaleInput) {
    logoScaleInput.addEventListener("input", function () {
      initializeWatermark(true);
    });
  }

  if (watermarkOpacityInput) {
    watermarkOpacityInput.addEventListener("input", renderWatermark);
  }

  if (watermarkRotationSlider) {
    watermarkRotationSlider.addEventListener("input", function () {
      renderWatermark();
      updateHiddenFields();
    });
  }

  pixelWidthInput.addEventListener("input", function () {
    state.activeDimension = "width";
    syncOutputDimensions("width");
  });

  pixelHeightInput.addEventListener("input", function () {
    state.activeDimension = "height";
    syncOutputDimensions("height");
  });

  window.addEventListener("resize", initializeCropBox);

  imageFileInput.addEventListener("change", function () {
    const file = imageFileInput.files && imageFileInput.files[0];
    if (!file) {
      return;
    }
    if (state.objectUrl) {
      URL.revokeObjectURL(state.objectUrl);
    }
    state.objectUrl = URL.createObjectURL(file);
    loadPreview(state.objectUrl);
  });

  syncOutputDimensions("width");
})();
