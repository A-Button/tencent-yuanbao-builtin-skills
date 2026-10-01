(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) Object.defineProperty(root, "PersonalityScoringV1", { value: api });
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const TRAITS = Object.freeze([
    "extraversion",
    "agreeableness",
    "conscientiousness",
    "neuroticism",
    "imagination"
  ]);
  const AXES = Object.freeze([
    Object.freeze({ key: "EI", trait: "extraversion", highLetter: "E", lowLetter: "I" }),
    Object.freeze({ key: "NS", trait: "imagination", highLetter: "N", lowLetter: "S" }),
    Object.freeze({ key: "FT", trait: "agreeableness", highLetter: "F", lowLetter: "T" }),
    Object.freeze({ key: "JP", trait: "conscientiousness", highLetter: "J", lowLetter: "P" })
  ]);

  function roundHalfUpRatio(numerator, denominator) {
    if (!Number.isInteger(numerator) || numerator < 0 || !Number.isInteger(denominator) || denominator <= 0) {
      throw new Error("取整参数无效");
    }
    return Math.floor((2 * numerator + denominator) / (2 * denominator));
  }

  function axisPercentage(sum, count) {
    if (!Number.isInteger(sum) || !Number.isInteger(count) || count <= 0 || sum < count || sum > count * 5) {
      throw new Error("维度总分无效");
    }
    return roundHalfUpRatio((sum - count) * 100, count * 4);
  }

  function answerFor(answers, itemId, itemIndex, itemCount) {
    if (Array.isArray(answers)) {
      if (answers.length !== itemCount) throw new Error(`答案数量必须为 ${itemCount}`);
      return answers[itemIndex];
    }
    if (answers instanceof Map) return answers.get(itemId);
    if (answers && typeof answers === "object") return answers[String(itemId)];
    throw new Error("答案必须是数组、Map 或题号对象");
  }

  function evaluateAssessment(spec, answers) {
    if (!spec || !Array.isArray(spec.items) || !Number.isInteger(spec.item_count) || spec.items.length !== spec.item_count) {
      throw new Error("测评规格无效");
    }
    const sums = Object.fromEntries(TRAITS.map((trait) => [trait, 0]));
    const counts = Object.fromEntries(TRAITS.map((trait) => [trait, 0]));
    const histogram = [0, 0, 0, 0, 0];

    spec.items.forEach((item, index) => {
      if (!item || item.id !== index + 1 || !TRAITS.includes(item.trait) || typeof item.reverse !== "boolean") {
        throw new Error(`题目 ${index + 1} 的计分键无效`);
      }
      const response = answerFor(answers, item.id, index, spec.item_count);
      if (!Number.isInteger(response) || response < 1 || response > 5) {
        throw new Error(`题目 ${item.id} 的答案无效`);
      }
      histogram[response - 1] += 1;
      sums[item.trait] += item.reverse ? 6 - response : response;
      counts[item.trait] += 1;
    });

    const scores = {};
    TRAITS.forEach((trait) => {
      if (counts[trait] <= 0) throw new Error(`缺少人格维度：${trait}`);
      scores[trait] = Object.freeze({
        sum: sums[trait],
        count: counts[trait],
        mean_x100: Math.round(sums[trait] * 100 / counts[trait])
      });
    });

    const uniqueResponseCount = histogram.filter((count) => count > 0).length;
    const quality = uniqueResponseCount === 1 ? "straight_lining" : "pass";
    const axes = AXES.map((axis) => {
      const score = scores[axis.trait];
      const high = axisPercentage(score.sum, score.count);
      const midpoint = score.count * 3;
      const letter = score.sum > midpoint ? axis.highLetter : score.sum < midpoint ? axis.lowLetter : "X";
      return Object.freeze({ ...axis, high, low: 100 - high, letter });
    });
    const typeCode = quality === "straight_lining" ? null : axes.map((axis) => axis.letter).join("");

    return Object.freeze({
      scores: Object.freeze(scores),
      histogram: Object.freeze(histogram),
      unique_response_count: uniqueResponseCount,
      quality,
      axes: Object.freeze(axes),
      type_code: typeCode
    });
  }

  function selectMascotTypeCodes(evaluation) {
    if (
      !evaluation
      || evaluation.quality !== "pass"
      || typeof evaluation.type_code !== "string"
      || !/^[EIX][NSX][FTX][JPX]$/.test(evaluation.type_code)
    ) {
      return Object.freeze([]);
    }
    const typeCode = evaluation.type_code;
    if (!typeCode.includes("X")) return Object.freeze([typeCode]);

    let highBoundary = "";
    let lowBoundary = "";
    Array.from(typeCode).forEach((letter, index) => {
      if (letter === "X") {
        highBoundary += AXES[index].highLetter;
        lowBoundary += AXES[index].lowLetter;
      } else {
        highBoundary += letter;
        lowBoundary += letter;
      }
    });
    return Object.freeze(
      highBoundary === lowBoundary ? [highBoundary] : [highBoundary, lowBoundary]
    );
  }

  function buildTransferModel(spec, evaluation) {
    if (!evaluation || !evaluation.scores || !Array.isArray(evaluation.axes)) throw new Error("计分结果无效");
    const axes = {};
    evaluation.axes.forEach((axis) => {
      axes[axis.key] = {
        [axis.highLetter]: axis.high,
        [axis.lowLetter]: axis.low,
        letter: axis.letter
      };
    });
    const bigFive = {};
    TRAITS.forEach((trait) => {
      bigFive[trait] = (evaluation.scores[trait].mean_x100 / 100).toFixed(2);
    });
    return {
      axes,
      big_five_mean_1_to_5: bigFive
    };
  }

  function formatTransferText(model) {
    if (!model || !model.axes || !model.big_five_mean_1_to_5) throw new Error("复制结果格式无效");
    return [
      "请根据以下本地人格测评结果做专业、非诊断性的解读，并优先讨论连续维度。",
      "PERSONALITY_RESULT_V1",
      JSON.stringify(model, null, 2)
    ].join("\n");
  }

  return Object.freeze({
    TRAITS,
    AXES,
    roundHalfUpRatio,
    axisPercentage,
    evaluateAssessment,
    selectMascotTypeCodes,
    buildTransferModel,
    formatTransferText
  });
});
