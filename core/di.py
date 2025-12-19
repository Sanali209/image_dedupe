from loguru import logger

class ServiceContainer:
    _instances = {}

    @classmethod
    def register(cls, interface, instance):
        """Register a singleton instance for an interface/class type."""
        logger.debug(f"DI: Registering {interface} -> {instance}")
        cls._instances[interface] = instance

    @classmethod
    def resolve(cls, interface):
        """Resolve a dependency."""
        if interface not in cls._instances:
            raise Exception(f"Service {interface} not registered in DI Container.")
        return cls._instances[interface]

    @classmethod
    def reset(cls):
        """Clear all registered services (useful for testing)."""
        cls._instances = {}
