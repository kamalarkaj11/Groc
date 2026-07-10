/* address_intelligence.js — Address Search, Autofill, Leaflet Map, Reverse Geocoding */

var AddressIntelligence = (function () {
  'use strict';

  var ADDRESS_SEARCH_URL = '/api/address/search/';
  var REVERSE_GEO_URL = '/api/address/reverse/';
  var SAVE_ADDRESS_URL = '/api/address/save/';
  var LIST_ADDRESSES_URL = '/api/address/list/';

  var DEFAULT_LAT = 20.5937;
  var DEFAULT_LNG = 78.9629;
  var DEFAULT_ZOOM = 5;

  var state = {
    searchInput: null,
    suggestionsContainer: null,
    mapContainer: null,
    map: null,
    marker: null,
    latInput: null,
    lngInput: null,
    addressInput: null,
    streetInput: null,
    areaInput: null,
    cityInput: null,
    districtInput: null,
    stateInput: null,
    countryInput: null,
    postalInput: null,
    houseNumberInput: null,
    localityInput: null,
    villageInput: null,
    townInput: null,
    placeIdInput: null,
    boundingBoxInput: null,
    displayNameInput: null,
    currentLocationBtn: null,
    locationStatusEl: null,
    selectedPlaceId: null,
    debounceTimer: null,
    abortController: null,
    isDragging: false,
  };

  function getCookie(name) {
    var value = null;
    if (document.cookie) {
      document.cookie.split(';').forEach(function (c) {
        c = c.trim();
        if (c.startsWith(name + '=')) value = decodeURIComponent(c.substring(name.length + 1));
      });
    }
    return value;
  }

  function csrfSafeMethod(method) {
    return /^(GET|HEAD|OPTIONS|TRACE)$/.test(method);
  }

  function getCsrfToken() {
    return getCookie('csrftoken');
  }

  function highlightMatch(text, query) {
    if (!query) return escapeHtml(text);
    var re = new RegExp('(' + escapeRegex(query) + ')', 'gi');
    return escapeHtml(text).replace(re, '<strong>$1</strong>');
  }

  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function showStatus(msg, isError) {
    if (!state.locationStatusEl) return;
    state.locationStatusEl.innerHTML = msg;
    state.locationStatusEl.className = 'addr-status ' + (isError ? 'addr-status-error' : 'addr-status-info');
    state.locationStatusEl.style.display = 'block';
  }

  function hideStatus() {
    if (!state.locationStatusEl) return;
    state.locationStatusEl.style.display = 'none';
    state.locationStatusEl.innerHTML = '';
  }

  // ── Search ──────────────────────────────────────────────────────

  function doSearch(query) {
    if (state.abortController) {
      state.abortController.abort();
    }
    state.abortController = new AbortController();

    if (!query || query.length < 2) {
      clearSuggestions();
      return;
    }

    var url = ADDRESS_SEARCH_URL + '?q=' + encodeURIComponent(query) + '&limit=8';
    fetch(url, {
      signal: state.abortController.signal,
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.results && data.results.length > 0) {
          renderSuggestions(data.results, query);
        } else {
          clearSuggestions();
          if (query.length >= 3) {
            showNoResults();
          }
        }
      })
      .catch(function (err) {
        if (err.name !== 'AbortError') {
          console.error('Address search failed:', err);
        }
      });
  }

  function renderSuggestions(results, query) {
    var container = state.suggestionsContainer;
    if (!container) return;
    container.innerHTML = '';
    container.style.display = 'block';

    results.forEach(function (item, idx) {
      var div = document.createElement('div');
      div.className = 'addr-suggestion-item';
      div.setAttribute('role', 'option');
      div.setAttribute('data-index', idx);
      div.tabIndex = -1;

      var icon = document.createElement('i');
      icon.className = 'bi bi-geo-alt-fill addr-suggestion-icon';

      var textSpan = document.createElement('span');
      textSpan.className = 'addr-suggestion-text';
      textSpan.innerHTML = highlightMatch(item.display_name || '', query);

      var typeSpan = document.createElement('span');
      typeSpan.className = 'addr-suggestion-type';
      typeSpan.textContent = item.type || item.category || '';

      div.appendChild(icon);
      div.appendChild(textSpan);
      if (typeSpan.textContent) div.appendChild(typeSpan);

      div.addEventListener('click', function () {
        selectAddress(item);
      });

      container.appendChild(div);
    });
  }

  function clearSuggestions() {
    if (state.suggestionsContainer) {
      state.suggestionsContainer.innerHTML = '';
      state.suggestionsContainer.style.display = 'none';
    }
  }

  function showNoResults() {
    var container = state.suggestionsContainer;
    if (!container) return;
    container.innerHTML = '';
    var div = document.createElement('div');
    div.className = 'addr-suggestion-item addr-no-results';
    div.innerHTML = '<i class="bi bi-search me-2"></i> Address not found. Try a different search.';
    container.appendChild(div);
    container.style.display = 'block';
  }

  // ── Select Address ─────────────────────────────────────────────

  function selectAddress(item) {
    clearSuggestions();
    state.selectedPlaceId = item.place_id;

    if (state.searchInput) {
      state.searchInput.value = item.display_name || '';
    }

    var lat = parseFloat(item.latitude);
    var lng = parseFloat(item.longitude);

    if (state.latInput) state.latInput.value = lat || '';
    if (state.lngInput) state.lngInput.value = lng || '';
    if (state.addressInput) state.addressInput.value = item.display_name || '';
    if (state.displayNameInput) state.displayNameInput.value = item.display_name || '';
    if (state.houseNumberInput) state.houseNumberInput.value = item.house_number || '';
    if (state.streetInput) state.streetInput.value = item.road || item.street || '';
    if (state.areaInput) state.areaInput.value = item.area || '';
    if (state.localityInput) state.localityInput.value = item.locality || '';
    if (state.villageInput) state.villageInput.value = item.village || '';
    if (state.townInput) state.townInput.value = item.town || '';
    if (state.cityInput) state.cityInput.value = item.city || '';
    if (state.districtInput) state.districtInput.value = item.district || '';
    if (state.stateInput) state.stateInput.value = item.state || '';
    if (state.countryInput) state.countryInput.value = item.country || 'India';
    if (state.postalInput) state.postalInput.value = item.postcode || '';
    if (state.placeIdInput) state.placeIdInput.value = item.place_id || '';
    if (state.boundingBoxInput) state.boundingBoxInput.value = item.bounding_box || '';

    if (state.map && lat && lng) {
      state.map.setView([lat, lng], 16, { animate: true });
      if (state.marker) {
        state.marker.setLatLng([lat, lng]);
      } else {
        state.marker = L.marker([lat, lng], { draggable: true }).addTo(state.map);
        state.marker.on('dragstart', function () { state.isDragging = true; });
        state.marker.on('dragend', onMarkerDragEnd);
      }
    }
  }

  // ── Marker Drag ────────────────────────────────────────────────

  function onMarkerDragEnd() {
    state.isDragging = false;
    var pos = state.marker.getLatLng();
    var lat = pos.lat.toFixed(6);
    var lng = pos.lng.toFixed(6);

    if (state.latInput) state.latInput.value = lat;
    if (state.lngInput) state.lngInput.value = lng;

    reverseGeocode(lat, lng);
  }

  function reverseGeocode(lat, lng) {
    showStatus('Fetching address for this location…');

    var url = REVERSE_GEO_URL + '?lat=' + lat + '&lon=' + lng;
    return fetch(url, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success !== false && data.display_name) {
          populateFromReverse(data);
          hideStatus();
          return data;
        } else {
          showStatus('Unable to resolve address for this location.', true);
          return null;
        }
      })
      .catch(function () {
        showStatus('Network error while fetching address.', true);
        return null;
      });
  }

  function populateFromReverse(data) {
    if (state.searchInput) state.searchInput.value = data.display_name || '';
    if (state.addressInput) state.addressInput.value = data.display_name || '';
    if (state.displayNameInput) state.displayNameInput.value = data.display_name || '';
    if (state.houseNumberInput) state.houseNumberInput.value = data.house_number || '';
    if (state.streetInput) state.streetInput.value = data.road || data.street || '';
    if (state.areaInput) state.areaInput.value = data.area || '';
    if (state.localityInput) state.localityInput.value = data.locality || '';
    if (state.villageInput) state.villageInput.value = data.village || '';
    if (state.townInput) state.townInput.value = data.town || '';
    if (state.cityInput) state.cityInput.value = data.city || '';
    if (state.districtInput) state.districtInput.value = data.district || '';
    if (state.stateInput) state.stateInput.value = data.state || '';
    if (state.countryInput) state.countryInput.value = data.country || 'India';
    if (state.postalInput) state.postalInput.value = data.postcode || '';
    if (state.placeIdInput) state.placeIdInput.value = data.place_id || '';
    if (state.boundingBoxInput) state.boundingBoxInput.value = data.bounding_box || '';
    if (state.latInput) state.latInput.value = data.latitude || '';
    if (state.lngInput) state.lngInput.value = data.longitude || '';
  }

  // ── Current Location ───────────────────────────────────────────

  function handleCurrentLocation() {
    if (!navigator.geolocation) {
      showStatus('Geolocation is not supported by your browser.', true);
      return;
    }

    showStatus('Requesting GPS location…');
    if (state.currentLocationBtn) state.currentLocationBtn.disabled = true;

    navigator.geolocation.getCurrentPosition(
      function (position) {
        var lat = position.coords.latitude.toFixed(6);
        var lng = position.coords.longitude.toFixed(6);
        showStatus('GPS fix obtained. Resolving address…');

        if (state.map) {
          state.map.setView([lat, lng], 16, { animate: true });
          if (state.marker) {
            state.marker.setLatLng([lat, lng]);
          } else {
            state.marker = L.marker([lat, lng], { draggable: true }).addTo(state.map);
            state.marker.on('dragstart', function () { state.isDragging = true; });
            state.marker.on('dragend', onMarkerDragEnd);
          }
        }

        if (state.latInput) state.latInput.value = lat;
        if (state.lngInput) state.lngInput.value = lng;

        reverseGeocode(lat, lng);

        if (state.currentLocationBtn) state.currentLocationBtn.disabled = false;
      },
      function (error) {
        if (state.currentLocationBtn) state.currentLocationBtn.disabled = false;
        var msg = '';
        switch (error.code) {
          case error.PERMISSION_DENIED:
            msg = 'Location permission denied. Please enter your address manually.';
            break;
          case error.POSITION_UNAVAILABLE:
            msg = 'GPS signal unavailable. Please try again.';
            break;
          case error.TIMEOUT:
            msg = 'Location request timed out. Please try again.';
            break;
          default:
            msg = 'Unable to fetch your location.';
        }
        showStatus(msg, true);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 }
    );
  }

  // ── Keyboard Navigation ────────────────────────────────────────

  function handleKeydown(e) {
    var container = state.suggestionsContainer;
    if (!container || container.style.display === 'none') return;

    var items = container.querySelectorAll('.addr-suggestion-item:not(.addr-no-results)');
    if (items.length === 0) return;

    var currentIndex = -1;
    items.forEach(function (item, idx) {
      if (item.classList.contains('addr-suggestion-active')) {
        currentIndex = idx;
        item.classList.remove('addr-suggestion-active');
      }
    });

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        currentIndex = Math.min(currentIndex + 1, items.length - 1);
        break;
      case 'ArrowUp':
        e.preventDefault();
        currentIndex = Math.max(currentIndex - 1, 0);
        break;
      case 'Enter':
        e.preventDefault();
        if (currentIndex >= 0 && items[currentIndex]) {
          items[currentIndex].click();
        }
        return;
      case 'Escape':
        e.preventDefault();
        clearSuggestions();
        if (state.searchInput) state.searchInput.blur();
        return;
      default:
        return;
    }

    if (items[currentIndex]) {
      items[currentIndex].classList.add('addr-suggestion-active');
      items[currentIndex].scrollIntoView({ block: 'nearest' });
    }
  }

  // ── Initialize Map ─────────────────────────────────────────────

  function initMap() {
    if (!state.mapContainer) return;

    var initialLat = parseFloat(state.latInput ? state.latInput.value : null) || DEFAULT_LAT;
    var initialLng = parseFloat(state.lngInput ? state.lngInput.value : null) || DEFAULT_LNG;

    if (typeof L === 'undefined') {
      console.warn('Leaflet not loaded. Delaying map init.');
      return;
    }

    state.map = L.map(state.mapContainer, {
      center: [initialLat, initialLng],
      zoom: state.latInput && state.latInput.value ? 16 : DEFAULT_ZOOM,
      zoomControl: true,
      scrollWheelZoom: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(state.map);

    if (state.latInput && state.latInput.value && state.lngInput && state.lngInput.value) {
      var lat = parseFloat(state.latInput.value);
      var lng = parseFloat(state.lngInput.value);
      if (!isNaN(lat) && !isNaN(lng)) {
        state.marker = L.marker([lat, lng], { draggable: true }).addTo(state.map);
        state.marker.on('dragstart', function () { state.isDragging = true; });
        state.marker.on('dragend', onMarkerDragEnd);
      }
    }

    setTimeout(function () {
      state.map.invalidateSize();
    }, 500);
  }

  // ── Public API ─────────────────────────────────────────────────

  function init(config) {
    state.searchInput = document.getElementById(config.searchInputId || 'addressSearchInput');
    state.suggestionsContainer = document.getElementById(config.suggestionsId || 'addressSuggestions');
    state.mapContainer = document.getElementById(config.mapId || 'addressMap');
    state.latInput = document.getElementById(config.latId || 'id_latitude');
    state.lngInput = document.getElementById(config.lngId || 'id_longitude');
    state.addressInput = document.getElementById(config.addressId || 'id_address');
    state.streetInput = document.getElementById(config.streetId || 'id_street');
    state.areaInput = document.getElementById(config.areaId || 'id_area');
    state.cityInput = document.getElementById(config.cityId || 'id_city');
    state.districtInput = document.getElementById(config.districtId || 'id_district');
    state.stateInput = document.getElementById(config.stateId || 'id_state');
    state.countryInput = document.getElementById(config.countryId || 'id_country');
    state.postalInput = document.getElementById(config.postalId || 'id_postal_code');
    state.houseNumberInput = document.getElementById(config.houseNumberId || 'id_house_number');
    state.localityInput = document.getElementById(config.localityId || 'id_locality');
    state.villageInput = document.getElementById(config.villageId || 'id_village');
    state.townInput = document.getElementById(config.townId || 'id_town');
    state.placeIdInput = document.getElementById(config.placeIdId || 'id_place_id');
    state.boundingBoxInput = document.getElementById(config.boundingBoxId || 'id_bounding_box');
    state.displayNameInput = document.getElementById(config.displayNameId || 'id_display_name');
    state.currentLocationBtn = document.getElementById(config.currentLocationBtnId || 'btnCurrentLocation');
    state.locationStatusEl = document.getElementById(config.statusId || 'addressStatus');

    if (state.searchInput) {
      state.searchInput.setAttribute('autocomplete', 'off');
      state.searchInput.addEventListener('input', function () {
        var query = state.searchInput.value.trim();
        clearTimeout(state.debounceTimer);
        state.debounceTimer = setTimeout(function () {
          doSearch(query);
        }, 500);
      });
      state.searchInput.addEventListener('keydown', handleKeydown);
      state.searchInput.addEventListener('blur', function () {
        setTimeout(clearSuggestions, 200);
      });
      state.searchInput.addEventListener('focus', function () {
        if (state.suggestionsContainer && state.suggestionsContainer.children.length > 0) {
          state.suggestionsContainer.style.display = 'block';
        }
      });
    }

    if (state.currentLocationBtn) {
      state.currentLocationBtn.addEventListener('click', handleCurrentLocation);
    }

    if (state.mapContainer) {
      if (document.readyState === 'complete') {
        initMap();
      } else {
        window.addEventListener('load', initMap);
      }
    }
  }

  function destroy() {
    if (state.map) {
      state.map.remove();
      state.map = null;
      state.marker = null;
    }
    if (state.abortController) {
      state.abortController.abort();
      state.abortController = null;
    }
    clearTimeout(state.debounceTimer);
  }

  return { init: init, destroy: destroy, selectAddress: selectAddress, reverseGeocode: reverseGeocode };

})();
