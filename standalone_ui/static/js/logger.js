export function createLogger(moduleName) {
    if (typeof moduleName !== 'string' || moduleName.trim().length === 0) {
        throw new Error('logger: moduleName (non-empty string) is required');
    }

    const prefix = () => {
        const ts = new Date().toISOString();
        return `[${ts}] [${moduleName}]`;
    };

    return {
        debug: (...args) => console.debug(prefix(), ...args),
        info: (...args) => console.info(prefix(), ...args),
        warn: (...args) => console.warn(prefix(), ...args),
        error: (...args) => console.error(prefix(), ...args),
    };
}

