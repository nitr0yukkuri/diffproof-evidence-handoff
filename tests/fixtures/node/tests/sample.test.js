const assert = require('node:assert/strict');
const test = require('node:test');

test('the sample test fixture verifies an expected value', () => {
  assert.equal('Hello, agent', `Hello, ${'agent'}`);
});
