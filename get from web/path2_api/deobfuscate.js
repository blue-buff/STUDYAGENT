// Deobfuscate the Z() function to extract string mappings
function Z() {
  var U = ['setDate', 'CPBoA', 'EuWuh', '2692915LPvLJc', 'EyJtp', 'BnmBC', 'alicfw', 'wAXWR', 'toGMTString', 'ZCtne', 'dRcWF', 'WPKcA', 'gsyGC', 'VdsWn', 'VOeWP', 'vkRGS', 'PKfKs', 'VIwmN', 'clientHeight', 'qGSHB', '6|2|0|4|7|8|1|3|5', '2382APyAnZ', 'eOxRB', 'NaTvv', 'aKLEt', 'getDate', 'JjGpV', 'location', 'uOefP', 'length', 'szlwY', 'cookie', 'WHFvT', 'host', 'wiGeS', '353784PLKrwL', 'BUlET', ';path=/', 'NQYEZ', 'tmuPq', 'CyuZJ', 'NQYEZ', 'protocol', 'split', 'reRGP', 'KdxMP', 'SLEuY', 'NRYtj', 'bGnGz', 'LRjWH', 'ngiRp', 'clientWidth', 'MeUzm', 'mGkxk', '11511150QPbmwW', '144ZPJzag', '1914666ufUThb', 'auTOZ', '1082904JoefgG', 'getElementById', 'YPShL', 'log', 'YNynO', 'mTySG', ';expires=', '3880AlRztD', 'NNQHb', '5|4|6|0|2|3|8|9|7|1', 'dLMKj', 'v1.200309.1', 'FLGyw', ';samesite=none;secure', 'bFSkT', 'zlyUs', 'ugWJY', 'Fbuli', 'ABLuu', 'fpiQy', 'RvZLO', 'vNwPb', 'DjXXN', 'hZCEl', 'https:', 'fyoal', 'dPGFj', '2|5|0|6|1|4|3', 'GiIZm', 'charCodeAt', 'alicfw_gfver', 'fzCyE', 'value', 'ubdGA', 'BEMgz', 'DHkIL', 'LzWrw', 'reload', 'parm_0', '1294479RTlfGo', 'VDyTo', 'ysIEr', '14CZcKYt'];
  Z = function () { return U; };
  return Z();
}

// The 'a' function maps hex codes to indices in the U array
function a(M, B) {
  var j = Z();
  return a = function (f, N) {
    f = f - 0xf4;
    var r = j[f];
    return r;
  }, a(M, B);
}

// Print all mappings
var arr = Z();
console.log("String array length:", arr.length);

// Decode all the a(x) calls by running through obfuscated values
// The hex values used in a() range from 0xf4 to 0x157
for (var i = 0xf4; i <= 0x157; i++) {
  var idx = i - 0xf4;
  if (idx < arr.length) {
    console.log(`a(0x${i.toString(16)}) = a(${i}) = [${idx}] = "${arr[idx]}"`);
  }
}
