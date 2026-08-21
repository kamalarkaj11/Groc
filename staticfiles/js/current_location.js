/* current_location.js — Geolocation + Reverse Geocoding for Profile */

(function () {
  'use strict';

  const LOCATION_API_URL = '/api/save-current-location/';
  const CSRF_TOKEN = document.querySelector('[name=csrfmiddlewaretoken]')?.value;

  let locationButton = null;
  let statusEl = null;
  let fields = {};

  /**
   * Initialize the "Use Current Location" feature on the edit profile page.
   */
  function initCurrentLocation() {
    locationButton = document.getElementById('btnUseCurrentLocation');
    if (!locationButton) return;

    statusEl = document.getElementById('locationStatus');

    // Gather the address fields to populate
    fields = {
      address: document.getElementById('id_address'),
      currentAddress: document.getElementById('id_current_address'),
      latitude: document.getElementById('id_latitude'),
      longitude: document.getElementById('id_longitude'),
      city: document.getElementById('id_city'),
      postalCode: document.getElementById('id_postal_code'),
      country: document.getElementById('id_country'),
      addressSource: document.getElementById('id_address_source'),
    };

    locationButton.addEventListener('click', handleGetLocation);
  }

  /**
   * Show a status message to the user.
   */
  function setStatus(msg, isError) {
    if (!statusEl) return;
    statusEl.innerHTML = msg;
    statusEl.className = isError
      ? 'alert alert-danger mt-2 small'
      : 'alert alert-info mt-2 small';
    statusEl.style.display = 'block';
  }

  /**
   * Clear the status message.
   */
  function clearStatus() {
    if (!statusEl) return;
    statusEl.style.display = 'none';
    statusEl.innerHTML = '';
  }

  /**
   * Handle the "Use Current Location" button click.
   */
  function handleGetLocation() {
    if (!navigator.geolocation) {
      setStatus('Geolocation is not supported by your browser. Please enter your address manually.', true);
      return;
    }

    setStatus('Requesting location permission…');
    locationButton.disabled = true;

    navigator.geolocation.getCurrentPosition(
      // Success callback
      function (position) {
        const lat = position.coords.latitude;
        const lng = position.coords.longitude;
        setStatus('Location obtained. Fetching address…');
        reverseGeocodeAndSave(lat, lng);
      },
      // Error callback
      function (error) {
        locationButton.disabled = false;
        switch (error.code) {
          case error.PERMISSION_DENIED:
            setStatus('Location permission denied. Please enable location access in your browser settings, or enter your address manually.', true);
            break;
          case error.POSITION_UNAVAILABLE:
            setStatus('GPS signal unavailable. Please try again or enter your address manually.', true);
            break;
          case error.TIMEOUT:
            setStatus('Location request timed out. Please try again or enter your address manually.', true);
            break;
          default:
            setStatus('An unknown error occurred. Please try again or enter your address manually.', true);
        }
      },
      {
        enableHighAccuracy: true,
        timeout: 15000,
        maximumAge: 60000,
      }
    );
  }

  /**
   * Reverse-geocode the coordinates using Nominatim via our API endpoint,
   * then fill the form fields.
   */
  function reverseGeocodeAndSave(lat, lng) {
    const payload = JSON.stringify({ latitude: lat, longitude: lng });

    fetch(LOCATION_API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': CSRF_TOKEN,
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: payload,
    })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) throw new Error(data.error || 'Failed to fetch address');
          return data;
        });
      })
      .then(function (data) {
        // Populate form fields
        if (fields.address) {
          fields.address.value = data.address || data.display_name || '';
        }
        if (fields.currentAddress) {
          fields.currentAddress.value = data.address || data.display_name || '';
        }
        if (fields.latitude) {
          fields.latitude.value = data.latitude || '';
        }
        if (fields.longitude) {
          fields.longitude.value = data.longitude || '';
        }
        if (fields.city) {
          fields.city.value = data.city || '';
        }
        if (fields.postalCode) {
          fields.postalCode.value = data.postcode || '';
        }
        if (fields.country) {
          fields.country.value = data.country || 'India';
        }
        if (fields.addressSource) {
          fields.addressSource.value = 'current_location';
        }

        // Also try to populate state if there's a state dropdown
        const stateField = document.getElementById('id_state');
        if (stateField && stateField.tagName === 'SELECT' && data.state) {
          const normalizedState = normalizeStateName(data.state);
          for (let i = 0; i < stateField.options.length; i++) {
            const opt = stateField.options[i];
            if (opt.text.toLowerCase() === normalizedState.toLowerCase() ||
                opt.value.toLowerCase() === normalizedState.toLowerCase()) {
              stateField.value = opt.value;
              break;
            }
          }
        }

        setStatus('Address fetched from your current location! <i class="bi bi-check-circle-fill text-success"></i>');
        locationButton.disabled = false;
      })
      .catch(function (err) {
        locationButton.disabled = false;
        setStatus('Error: ' + err.message + '. Please enter your address manually.', true);
      });
  }

  /**
   * Normalize a state name (e.g. "Telangana" → "Telangana") for matching
   * against the IndianState choices.
   */
  function normalizeStateName(name) {
    if (!name) return '';
    const map = {
      'andhra pradesh': 'Andhra Pradesh',
      'telangana': 'Telangana',
      'telengana': 'Telangana',
      'maharashtra': 'Maharashtra',
      'karnataka': 'Karnataka',
      'tamil nadu': 'Tamil Nadu',
      'kerala': 'Keral',
      'keral': 'Keral',
      'delhi': 'Delhi',
      'national capital territory of delhi': 'Delhi',
      'goa': 'Goa',
      'gujarat': 'Gujarat',
      'rajasthan': 'Rajasthan',
      'punjab': 'Punjab',
      'haryana': 'Haryana',
      'uttar pradesh': 'Uttar Pradesh',
      'bihar': 'Bihar',
      'west bengal': 'West Bengal',
      'odisha': 'Odisha',
      'madhya pradesh': 'Madhya Pradesh',
      'jharkhand': 'Jharkhand',
      'chhattisgarh': 'Chhattisgarh',
      'assam': 'Assam',
      'himachal pradesh': 'Himachal Pradesh',
      'uttarakhand': 'Uttarakhand',
      'jammu and kashmir': 'Jammu & Kashmir',
      'jammu & kashmir': 'Jammu & Kashmir',
      'ladakh': 'Ladakh',
      'arunachal pradesh': 'Arunachal Pradesh',
      'manipur': 'Manipur',
      'meghalaya': 'Meghalaya',
      'mizoram': 'Mizoram',
      'nagaland': 'Nagaland',
      'sikkim': 'Sikkim',
      'tripura': 'Tripura',
      'puducherry': 'Puducherry',
      'chandigarh': 'Chandigarh',
      'andaman and nicobar': 'Andaman & Nicobar',
      'andaman & nicobar': 'Andaman & Nicobar',
      'dadra and nagar haveli and daman and diu': 'Dadra & Nagar Haveli and Daman & Diu',
      'dadra & nagar haveli and daman & diu': 'Dadra & Nagar Haveli and Daman & Diu',
    };
    const key = name.trim().toLowerCase();
    return map[key] || name;
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCurrentLocation);
  } else {
    initCurrentLocation();
  }
})();