#![forbid(unsafe_code)]

use std::sync::RwLock;

use atena_bus_core::{RouterError, SubscriptionId, TopicRouter as CoreRouter};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;

fn router_error(error: RouterError) -> PyErr {
    match error {
        RouterError::Topic(inner) => PyValueError::new_err(inner.to_string()),
        RouterError::CapacityExhausted => PyRuntimeError::new_err(error.to_string()),
    }
}

fn poisoned() -> PyErr {
    PyRuntimeError::new_err("topic router state is poisoned")
}

#[pyclass(frozen, module = "atena_native")]
#[derive(Debug, Default)]
struct TopicRouter {
    inner: RwLock<CoreRouter>,
}

#[pymethods]
impl TopicRouter {
    #[new]
    fn new() -> Self {
        Self::default()
    }

    fn subscribe(&self, pattern: &str) -> PyResult<SubscriptionId> {
        self.inner
            .write()
            .map_err(|_| poisoned())?
            .subscribe(pattern)
            .map_err(router_error)
    }

    fn unsubscribe(&self, id: SubscriptionId) -> PyResult<bool> {
        Ok(self.inner.write().map_err(|_| poisoned())?.unsubscribe(id))
    }

    fn route(&self, py: Python<'_>, topic: &str) -> PyResult<Vec<SubscriptionId>> {
        py.detach(|| {
            self.inner
                .read()
                .map_err(|_| poisoned())?
                .route(topic)
                .map_err(router_error)
        })
    }

    fn __len__(&self) -> PyResult<usize> {
        Ok(self.inner.read().map_err(|_| poisoned())?.len())
    }
}

#[pyfunction]
fn matches(pattern: &str, topic: &str) -> bool {
    atena_bus_core::matches(pattern, topic)
}

#[pyfunction]
fn valid_topic(topic: &str) -> bool {
    atena_bus_core::valid_topic(topic)
}

#[pyfunction]
fn valid_pattern(pattern: &str) -> bool {
    atena_bus_core::valid_pattern(pattern)
}

#[pyfunction]
fn valid_origin(origin: &str) -> bool {
    atena_bus_core::valid_origin(origin)
}

#[pyfunction]
#[pyo3(signature = (text, allowed = ""))]
fn detect_language(py: Python<'_>, text: &str, allowed: &str) -> Option<(String, f64, bool)> {
    py.detach(|| {
        let codes: Vec<&str> = allowed
            .split(',')
            .map(str::trim)
            .filter(|c| !c.is_empty())
            .collect();
        atena_langid::detect(text, &codes).map(|g| (g.code.to_owned(), g.confidence, g.reliable))
    })
}

#[pyfunction]
fn supported_languages() -> Vec<&'static str> {
    atena_langid::supported()
}

#[pymodule(gil_used = false)]
fn atena_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("MAX_SUBSCRIPTIONS", atena_bus_core::MAX_SUBSCRIPTIONS)?;
    m.add_class::<TopicRouter>()?;
    m.add_function(wrap_pyfunction!(matches, m)?)?;
    m.add_function(wrap_pyfunction!(valid_topic, m)?)?;
    m.add_function(wrap_pyfunction!(valid_pattern, m)?)?;
    m.add_function(wrap_pyfunction!(valid_origin, m)?)?;
    m.add_function(wrap_pyfunction!(detect_language, m)?)?;
    m.add_function(wrap_pyfunction!(supported_languages, m)?)?;
    Ok(())
}
