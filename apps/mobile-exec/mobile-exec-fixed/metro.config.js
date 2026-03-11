const { getDefaultConfig } = require('expo/metro-config');
const config = getDefaultConfig(__dirname);
config.resolver.sourceExts.push('cjs');
config.transformer = {
  ...config.transformer,
  unstable_allowRequireContext: true,
};
config.resolver.unstable_enablePackageExports = false;
module.exports = config;
