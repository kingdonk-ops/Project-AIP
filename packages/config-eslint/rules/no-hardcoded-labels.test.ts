// TERMS-07: the no-hardcoded-labels rule, against the real config/terms/en-AU dictionary.
import { RuleTester } from "eslint";
import { afterAll, describe, it } from "vitest";

import rule from "./no-hardcoded-labels.js";

RuleTester.afterAll = afterAll;
RuleTester.describe = describe;
RuleTester.it = it;
RuleTester.itOnly = it.only;

const tester = new RuleTester({
  languageOptions: { parserOptions: { ecmaFeatures: { jsx: true } } },
});

const error = (term: string, key: string) => ({
  messageId: "hardcoded",
  data: { term, key },
});

tester.run("no-hardcoded-labels", rule, {
  valid: [
    "<span>{t('record.type.ncr')}</span>",
    "<span>NCRs and Variations</span>", // whole words only
    "<span>an ncr</span>", // capitals match case-sensitively
    "<input aria-label={t('record.type.ncr')} />",
    '<Tag kind="NCR" />', // not a label prop
    "const x = 'NCR';", // plain strings outside JSX label props are the Python scanner's job
  ],
  invalid: [
    { code: "<span>NCR</span>", errors: [error("NCR", "record.type.ncr")] },
    { code: "<p>Raise a VARIATION</p>", errors: [error("Variation", "record.type.variation")] },
    { code: '<button aria-label="ITP" />', errors: [error("ITP", "forms.kind.itp")] },
    { code: "<input placeholder={'MEWP'} />", errors: [error("MEWP", "access.method.mewp")] },
    { code: "<Field label={`NCR`} />", errors: [error("NCR", "record.type.ncr")] },
    { code: '<abbr title="NCR">x</abbr>', errors: [error("NCR", "record.type.ncr")] },
    { code: "<span>{'NCR'}</span>", errors: [error("NCR", "record.type.ncr")] },
    { code: "<>{`ITP`}</>", errors: [error("ITP", "forms.kind.itp")] },
  ],
});
